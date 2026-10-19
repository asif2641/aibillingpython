"""ledger/services.py
==================
Business logic for payment recording, party running ledger (Khata), and CSV statement exports.
"""

import csv
import io
from decimal import Decimal
from typing import Any, Dict, List

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from billing.utils import money_round
from bills.models import Bill
from ledger.models import Payment
from parties.models import Party


def record_payment(
    party: Party,
    amount: Decimal,
    bill: Bill | None = None,
    payment_date=None,
    payment_method: str = "cash",
    reference: str = "",
    notes: str = "",
    created_by=None,
) -> Payment:
    """Record a payment towards a party's account or allocated to a specific bill.

    Rules:
    - amount must be greater than zero.
    - If bill is provided, bill.party must match party.
    - amount is rounded using money_round().
    - Updates bill.amount_paid and transitions bill.payment_status ('Unpaid', 'Partially Paid', 'Paid').
    """
    if amount is None or Decimal(str(amount)) <= Decimal("0.00"):
        raise ValidationError("Payment amount must be greater than zero.")

    rounded_amount = money_round(Decimal(str(amount)))

    if bill is not None and bill.party != party and getattr(bill, "customer", None) != party:
        raise ValidationError("Bill party does not match payment party.")

    if payment_date is None:
        payment_date = timezone.now().date()

    payment = Payment.objects.create(
        party=party,
        bill=bill,
        amount=rounded_amount,
        payment_date=payment_date,
        payment_method=payment_method,
        reference=reference,
        notes=notes,
        created_by=created_by,
    )

    if bill is not None:
        bill.amount_paid = money_round(bill.amount_paid + rounded_amount)
        if bill.amount_paid >= bill.grand_total:
            bill.payment_status = Bill.PaymentStatus.PAID
        elif bill.amount_paid > Decimal("0.00"):
            bill.payment_status = Bill.PaymentStatus.PARTIALLY_PAID
        else:
            bill.payment_status = Bill.PaymentStatus.UNPAID
        bill.save(update_fields=["amount_paid", "payment_status"])

    return payment


def get_party_ledger_statement(party: Party, user=None) -> Dict[str, Any]:
    """Calculate running ledger balance and chronological transaction timeline (Khata)."""
    from django.db.models import Q

    bill_filter = (Q(party=party) | Q(customer=party)) & Q(is_deleted=False)
    pay_filter = {"party": party, "is_deleted": False}
    if user is not None and not getattr(user, "is_superuser", False):
        bill_filter &= Q(created_by=user)
        pay_filter["created_by"] = user

    bills = (
        Bill.objects.filter(bill_filter)
        .distinct()
        .prefetch_related("items")
        .order_by("bill_date", "id")
    )
    payments = Payment.objects.filter(**pay_filter).order_by("payment_date", "id")

    timeline: List[Dict[str, Any]] = []

    for bill in bills:
        desc = ", ".join([it.item_name for it in bill.items.all()[:3]]) or _("Invoice")
        timeline.append(
            {
                "date": bill.bill_date,
                "sort_order": (bill.bill_date, 0, bill.id),
                "type": "bill",
                "reference": bill.invoice_no or f"BILL-{bill.pk}",
                "description": desc,
                "billed_amount": bill.grand_total,
                "paid_amount": Decimal("0.00"),
                "bill_id": bill.pk,
                "payment_id": None,
            }
        )

    for pay in payments:
        timeline.append(
            {
                "date": pay.payment_date,
                "sort_order": (pay.payment_date, 1, pay.id),
                "type": "payment",
                "reference": pay.reference or f"TXN-{pay.pk}",
                "description": f"{pay.get_payment_method_display()} - {pay.notes}"
                if pay.notes
                else pay.get_payment_method_display(),
                "billed_amount": Decimal("0.00"),
                "paid_amount": pay.amount,
                "bill_id": pay.bill_id,
                "payment_id": pay.pk,
            }
        )

    # Sort strictly by date then sequence
    timeline.sort(key=lambda x: x["sort_order"])

    running_balance = Decimal("0.00")
    total_billed = Decimal("0.00")
    total_paid = Decimal("0.00")

    for entry in timeline:
        total_billed += entry["billed_amount"]
        total_paid += entry["paid_amount"]
        running_balance += entry["billed_amount"] - entry["paid_amount"]
        entry["running_balance"] = money_round(running_balance)

    net_balance = money_round(total_billed - total_paid)

    # Balance categorization
    if party.party_type == Party.PartyType.CUSTOMER:
        if net_balance > Decimal("0.00"):
            balance_type = "receivable"
            balance_label = _("You will receive Rs. %(amount)s") % {"amount": net_balance}
        elif net_balance < Decimal("0.00"):
            balance_type = "advance"
            balance_label = _("Advance received Rs. %(amount)s") % {"amount": abs(net_balance)}
        else:
            balance_type = "settled"
            balance_label = _("Account Settled")
    else:  # Vendor or Both
        if net_balance > Decimal("0.00"):
            balance_type = "payable"
            balance_label = _("You owe Rs. %(amount)s") % {"amount": net_balance}
        elif net_balance < Decimal("0.00"):
            balance_type = "advance"
            balance_label = _("Advance paid Rs. %(amount)s") % {"amount": abs(net_balance)}
        else:
            balance_type = "settled"
            balance_label = _("Account Settled")

    return {
        "party": party,
        "total_billed": money_round(total_billed),
        "total_paid": money_round(total_paid),
        "net_balance": net_balance,
        "balance": net_balance,
        "balance_type": balance_type,
        "balance_label": balance_label,
        "entries": timeline,
    }


def generate_ledger_csv(party: Party, user=None) -> str:
    """Export party Khata ledger entries to CSV string format."""
    statement = get_party_ledger_statement(party, user=user)
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        ["Date", "Type", "Reference", "Description", "Billed", "Paid", "Running Balance"]
    )
    for entry in statement["entries"]:
        writer.writerow(
            [
                entry["date"].strftime("%Y-%m-%d"),
                entry["type"].capitalize(),
                entry["reference"],
                entry["description"],
                str(entry["billed_amount"]),
                str(entry["paid_amount"]),
                str(entry["running_balance"]),
            ]
        )

    return output.getvalue()


def get_all_parties_ledger_summary(
    party_type_filter: str = "all", search_query: str = "", user=None
) -> Dict[str, Any]:
    """Calculate aggregated ledger balances (receivables, payables) across active parties."""
    parties_qs = Party.objects.filter(is_active=True)
    if user is not None and not getattr(user, "is_superuser", False):
        parties_qs = parties_qs.filter(user=user)
    parties_qs = parties_qs.order_by("name")

    total_receivable = Decimal("0.00")
    total_payable = Decimal("0.00")
    party_summaries = []

    for party in parties_qs:
        stmt = get_party_ledger_statement(party, user=user)
        bal = stmt["net_balance"]
        b_type = stmt["balance_type"]

        # Track global accounting totals
        if b_type == "receivable":
            total_receivable += bal
        elif b_type == "payable":
            total_payable += bal

        # Filter for display
        if party_type_filter == "vendor" and party.party_type not in ("vendor", "both"):
            continue
        if party_type_filter == "customer" and party.party_type not in ("customer", "both"):
            continue

        if search_query:
            q_lower = search_query.lower()
            match = (
                q_lower in party.name.lower()
                or (party.urdu_name and q_lower in party.urdu_name.lower())
                or (party.phone and q_lower in party.phone.lower())
            )
            if not match:
                continue

        party_summaries.append(
            {
                "party": party,
                "statement": stmt,
                "total_billed": stmt["total_billed"],
                "total_paid": stmt["total_paid"],
                "net_balance": bal,
                "balance_type": b_type,
                "balance_label": stmt["balance_label"],
                "entries_count": len(stmt["entries"]),
            }
        )

    return {
        "party_summaries": party_summaries,
        "total_receivable": money_round(total_receivable),
        "total_payable": money_round(total_payable),
        "net_balance": money_round(total_receivable - total_payable),
        "total_accounts_count": len(party_summaries),
    }
