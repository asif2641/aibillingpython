# Golden Bills — AI Extraction Test Set

This folder is used by the QA Agent to measure AI extraction accuracy.

## How It Works

1. Put real bill images in subfolders here (one subfolder per bill).
2. Next to each image, place a `expected.json` file with the correct extraction values.
3. The QA Agent runs `pytest tests/test_golden_bills.py` which scans every bill and compares the result to `expected.json`.
4. Accuracy is reported per field (vendor name, date, grand total, each item's quantity, unit, price).

## Pass Requirements

| Field | Required Accuracy |
|-------|------------------|
| Grand total | ≥ 95% |
| Date | ≥ 95% |
| Line items (printed bills) | ≥ 90% |
| Line items (handwritten bills) | Track and improve; no hard floor at start |

**Any change to scanning code or the AI prompt must NOT lower these scores.**

## Bill Categories to Include (collect 20–30 total)

- [ ] 5 × printed shop receipts (thermal paper)
- [ ] 5 × printed invoices (formatted, multi-item)
- [ ] 5 × handwritten bills (Urdu)
- [ ] 5 × handwritten bills (English or mixed)
- [ ] 3 × multi-page bills (2–3 pages each)
- [ ] 3 × blurry or skewed scans
- [ ] 2 × utility bills / bank statements
- [ ] 2 × screenshot of a digital invoice

## Subfolder Structure

```
docs/GOLDEN_BILLS/
  bill-001-printed-grocery/
    image.jpg
    expected.json
  bill-002-handwritten-urdu/
    image.jpg
    expected.json
  ...
```

## expected.json Format

```json
{
  "vendor_name": "Al-Madina General Store",
  "date": "2026-09-15",
  "grand_total": "1250.00",
  "items": [
    { "name": "Sugar", "quantity": "2", "unit": "kg", "unit_price": "150.00", "line_total": "300.00" }
  ]
}
```

Only include fields you are confident about from the real bill.
