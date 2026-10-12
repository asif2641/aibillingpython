"""
billing/utils.py
================
Shared money helpers for the aibilling project.

ALL rounding in the project must go through money_round().
Never use float for money. Always use Decimal.

Usage:
    from billing.utils import money_round
    from decimal import Decimal

    total = money_round(Decimal("1.005") * 3)  # → Decimal("3.02")
"""

from decimal import ROUND_HALF_UP, Decimal

PLACES = Decimal("0.01")


def money_round(value: Decimal) -> Decimal:
    """Round a Decimal to 2 decimal places using ROUND_HALF_UP.

    Use this function everywhere money is rounded. Never round inline.
    This is the single source of truth for monetary rounding in the project.

    Args:
        value: The monetary value to round. Accepts Decimal, int, or str.
               Float inputs are converted via str() to avoid float precision issues.

    Returns:
        A Decimal rounded to 2 decimal places using ROUND_HALF_UP.

    Examples:
        >>> money_round(Decimal("1.005"))
        Decimal('1.01')
        >>> money_round(Decimal("2.344"))
        Decimal('2.34')
        >>> money_round(Decimal("2.345"))
        Decimal('2.35')
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(PLACES, rounding=ROUND_HALF_UP)
