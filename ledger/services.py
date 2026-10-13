"""ledger/services.py
==================
Business logic for payment recording and ledger operations.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

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

    if bill is not None and bill.party != party:
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
