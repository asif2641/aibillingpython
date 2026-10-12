# Money and Data Rules

These rules prevent the most expensive and hardest-to-find bugs. Every agent must follow them.

## 1. Use Decimal for All Money and Quantities

- **Python:** always use `from decimal import Decimal, ROUND_HALF_UP`. Never use `float`.
- **Django model fields:** always use `DecimalField(max_digits=14, decimal_places=2)` for money, `DecimalField(max_digits=12, decimal_places=4)` for quantities.
- **Why float is banned:** `0.1 + 0.2` in float equals `0.30000000000000004`, not `0.30`. A billing app with float will silently produce wrong totals.

## 2. Rounding — One Place, One Rule

- Rounding rule: **2 decimal places, ROUND_HALF_UP**.
- There is **one shared helper function** for rounding. All code calls that helper. Never write rounding logic inline.

```python
# billing/utils.py  ← the only place rounding lives
from decimal import Decimal, ROUND_HALF_UP

PLACES = Decimal("0.01")

def money_round(value: Decimal) -> Decimal:
    """Round a Decimal to 2 places using ROUND_HALF_UP. Use this everywhere."""
    return value.quantize(PLACES, rounding=ROUND_HALF_UP)
```

## 3. Totals Are Always Recalculated Server-Side

- **Never trust** totals sent from the browser form or from the AI extraction.
- The server always recalculates: `line_total = quantity × unit_price − discount + tax`; `grand_total = subtotal − discount + tax + other_charges`.
- Browser/HTMX may show a live preview, but the database stores only the server-calculated value.

## 4. Dates and Time Zones

- Store all dates and datetimes in **UTC** in the database (Django default).
- Display to the user in the **shop's time zone** (from `ShopProfile.timezone`).
- Store `bill_date` as a `DateField`, not a string.
- Never store a date as a string like `"12/10/2026"`.

## 5. Every Money Table Needs These Tests

A table that stores money must have passing tests for:

- [ ] Correct line total: `quantity × unit_price = line_total`
- [ ] Correct subtotal: `sum(line_totals) = subtotal`
- [ ] Correct discount application
- [ ] Correct tax application
- [ ] Correct grand total
- [ ] Correct balance/credit after payment
- [ ] Rounding: a test case that exercises the rounding rule (e.g., 3 × £1.005 = £3.02 not £3.015)

## 6. Soft Delete — Never Hard Delete Financial Records

- Bills, payments, and ledger entries use **soft delete** only.
- Add `is_deleted = BooleanField(default=False)` and `deleted_at = DateTimeField(null=True)` to every financial model.
- Default queryset manager must filter out `is_deleted=True`.
- Super Admin can restore from trash within 30 days.
- Only the Super Admin can permanently purge a trashed record, and only via a deliberate action with a confirmation dialog.

## 7. Fuzzy Party Matching — Never Auto-Merge When Unsure

- Fuzzy match threshold: score ≥ 90 → auto-match. Score 70–89 → show "Is this the same as …?" confirmation. Score < 70 → create a new party.
- Log every auto-match decision in `ActivityLog`.
- Never silently merge two parties. One wrong merge means wrong ledger balances for both.

## 8. Pagination and Indexing

- Every list view that may return more than 20 rows **must** be paginated (default page size: 25).
- Every `filter()` or `order_by()` on `bill_date`, `party`, `category`, `invoice_no`, `normalized_name` must have a matching database index.
- Watch for N+1 queries: use `select_related` and `prefetch_related` appropriately.
