"""bills/services.py
================
Business logic and total calculation service for bills.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError

from billing.utils import money_round
from bills.models import Bill


def recalculate_bill_totals(bill: Bill) -> Bill:
    """Recalculate line totals, subtotal, and grand total for a bill.

    Rules:
    - line_total = money_round(quantity * unit_price)
    - subtotal = money_round(sum(line_totals))
    - discount >= 0 (negative raises ValidationError)
    - tax >= 0 (negative raises ValidationError)
    - grand_total = money_round(subtotal - discount + tax), clamped to 0.00 if negative.

    Saves all modified items and the bill instance.
    """
    if bill.discount < Decimal("0.00"):
        raise ValidationError("Discount cannot be negative.")
    if bill.tax < Decimal("0.00"):
        raise ValidationError("Tax cannot be negative.")

    subtotal = Decimal("0.00")

    for item in bill.items.all():
        raw_lt = item.quantity * item.unit_price
        integer_cand = Decimal(str(round(float(raw_lt))))
        # If bill total has no decimal (integer) but multiplying qty * rounded unit_price
        # produces a rounding artifact (e.g. 6 * 21.67 = 130.02), ignore decimal and round to integer
        max_diff = max(Decimal("0.05"), money_round(item.quantity * Decimal("0.0055")))
        if (
            item.quantity > Decimal("1.00")
            and abs(raw_lt - integer_cand) <= max_diff
            and money_round(integer_cand / item.quantity) == item.unit_price
        ):
            line_total = integer_cand
        else:
            line_total = money_round(raw_lt)

        if item.line_total != line_total:
            item.line_total = line_total
            item.save(update_fields=["line_total"])
        subtotal += line_total

    bill.subtotal = money_round(subtotal)
    grand_total = money_round(bill.subtotal - bill.discount + bill.tax)
    if grand_total < Decimal("0.00"):
        grand_total = Decimal("0.00")

    bill.grand_total = grand_total
    bill.save(update_fields=["subtotal", "grand_total"])
    return bill
