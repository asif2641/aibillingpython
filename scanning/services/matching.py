"""scanning/services/matching.py
==============================
Fuzzy party resolution and automatic category suggestions from bill scans.
"""

from typing import Any, Dict, List, Optional, Tuple

from categories.models import Category
from parties.models import Party
from parties.services import match_or_create_party

CATEGORY_KEYWORD_MAP = {
    "Medical": [
        "panadol",
        "augmentin",
        "tablet",
        "syrup",
        "capsule",
        "medicine",
        "pharmacy",
        "injection",
        "ointment",
        "drops",
        "bandage",
    ],
    "Grocery": [
        "flour",
        "atta",
        "rice",
        "oil",
        "ghee",
        "sugar",
        "tea",
        "soap",
        "milk",
        "biscuit",
        "daal",
        "pulse",
        "chilli",
        "masala",
    ],
    "Fuel": ["petrol", "diesel", "cng", "lpg", "fuel", "gasoline", "mobil"],
    "Utilities": [
        "electricity",
        "lesco",
        "kelectric",
        "k-electric",
        "wapda",
        "gas",
        "sngpl",
        "ssgc",
        "ptcl",
        "water",
        "bill",
    ],
    "Electronics": [
        "cable",
        "wire",
        "bulb",
        "led",
        "switch",
        "plug",
        "fan",
        "battery",
        "charger",
        "adapter",
        "mobile",
        "screen",
    ],
    "Stationery": [
        "paper",
        "pen",
        "pencil",
        "notebook",
        "stapler",
        "envelope",
        "file",
        "tape",
        "folder",
        "copy",
        "print",
    ],
    "Restaurant": [
        "biryani",
        "karahi",
        "roti",
        "naan",
        "burger",
        "pizza",
        "tea",
        "coffee",
        "roll",
        "lunch",
        "dinner",
    ],
    "Construction": [
        "cement",
        "sand",
        "bricks",
        "iron",
        "steel",
        "paint",
        "pipes",
        "tiles",
        "gravel",
    ],
}


def resolve_scan_party(
    party_data: Optional[Dict[str, Any]],
    party_type: str = Party.PartyType.VENDOR,
    user: Any = None,
) -> Tuple[Party, bool]:
    """Match existing party or create a new party from extracted AI vendor/customer fields.

    Returns:
        (party_instance, is_newly_created)
    """
    if not party_data or not isinstance(party_data, dict):
        # Default fallback party
        fallback_kwargs = {
            "name": "Cash / Unspecified",
            "party_type": party_type,
        }
        if user is not None:
            fallback_kwargs["user"] = user
        fallback, is_new = Party.objects.get_or_create(**fallback_kwargs)
        return fallback, is_new

    name = party_data.get("name") or "Unspecified Vendor"
    urdu_name = party_data.get("urdu_name") or ""
    phone = party_data.get("phone") or ""
    address = party_data.get("address") or ""
    tax_number = party_data.get("tax_no") or ""

    import re

    if re.search(r"[\u0600-\u06FF]", name) and not urdu_name:
        urdu_name = name

    party_filter = {"name__iexact": name.strip()}
    if user is not None:
        party_filter["user"] = user
    existing_before = Party.objects.filter(**party_filter).first()
    party = match_or_create_party(
        name=name,
        phone=phone,
        party_type=party_type,
        urdu_name=urdu_name,
        address=address,
        tax_number=tax_number,
        user=user,
    )
    update_fields = []
    if urdu_name and not party.urdu_name:
        party.urdu_name = urdu_name
        update_fields.append("urdu_name")
    if phone and not party.phone:
        party.phone = str(phone).strip()
        update_fields.append("phone")
    if address and not party.address:
        party.address = str(address).strip()
        update_fields.append("address")
    if tax_number and not party.tax_number:
        party.tax_number = str(tax_number).strip()
        update_fields.append("tax_number")
    if update_fields:
        party.save(update_fields=update_fields)

    is_new = existing_before is None
    return party, is_new


def suggest_bill_category(
    suggested_name: Optional[str],
    items: List[Dict[str, Any]],
) -> Optional[Category]:
    """Identify the most likely Category based on AI suggestion or item keywords."""
    # 1. Match directly against category name or urdu_name
    if suggested_name and isinstance(suggested_name, str):
        cat = (
            Category.objects.filter(is_archived=False)
            .filter(models_name__iexact=suggested_name.strip())
            .first()
            if hasattr(Category.objects, "models_name")
            else None
        )

        cat = Category.objects.filter(
            is_archived=False, name__iexact=suggested_name.strip()
        ).first()
        if cat:
            return cat
        cat = Category.objects.filter(
            is_archived=False, urdu_name__icontains=suggested_name.strip()
        ).first()
        if cat:
            return cat

    # 2. Inspect item names for keyword patterns
    item_text = " ".join([str(it.get("name", "")).lower() for it in items])

    for cat_name, keywords in CATEGORY_KEYWORD_MAP.items():
        if any(kw in item_text for kw in keywords):
            cat = Category.objects.filter(is_archived=False, name__iexact=cat_name).first()
            if cat:
                return cat

    # Fallback to 'Other' or first active category
    return Category.objects.filter(is_archived=False, name__iexact="Other").first()
