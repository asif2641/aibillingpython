"""parties/services.py
===================
Business logic and fuzzy matching service for parties.
"""

from __future__ import annotations

import difflib
import re

from django.core.exceptions import ValidationError

from parties.models import Party


def normalize_phone(phone: str | None) -> str:
    """Normalize phone number to standard digits format for matching."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if digits.startswith("92") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits


def match_or_create_party(
    name: str | None,
    phone: str | None = None,
    party_type: str = "vendor",
    urdu_name: str = "",
    email: str = "",
    address: str = "",
    tax_number: str = "",
    notes: str = "",
    **kwargs,
) -> Party:
    """Match an existing party using phone number or fuzzy name matching, or create a new one.

    Matching logic:
    1. Phone match: If phone provided, checks against existing parties with normalized phone numbers.
    2. Name match: Uses difflib.SequenceMatcher.
       - similarity >= 0.90 -> return existing party.
       - similarity < 0.70 -> creates new party.
    3. If no existing match reaches the >= 0.90 threshold, creates and returns a new party.

    Raises:
        ValidationError: If name is None or empty.
    """
    if not name or not str(name).strip():
        raise ValidationError("Party name is required.")

    clean_name = str(name).strip()
    norm_phone = normalize_phone(phone)

    active_parties = Party.objects.filter(is_active=True)

    # 1. Match by phone if phone is provided
    if norm_phone:
        for party in active_parties:
            if party.phone and normalize_phone(party.phone) == norm_phone:
                return party

    # 2. Match by name or Urdu name
    best_match: Party | None = None
    best_score = 0.0

    clean_name_lower = clean_name.lower()

    for party in active_parties:
        score_en = difflib.SequenceMatcher(
            None, clean_name_lower, party.name.strip().lower()
        ).ratio()

        score_ur = 0.0
        if party.urdu_name:
            score_ur = difflib.SequenceMatcher(None, clean_name, party.urdu_name.strip()).ratio()

        score = max(score_en, score_ur)
        if score > best_score:
            best_score = score
            best_match = party

    if best_match is not None and best_score >= 0.90:
        fields_to_update = []
        if phone and not best_match.phone:
            best_match.phone = str(phone).strip()
            fields_to_update.append("phone")
        if address and not best_match.address:
            best_match.address = str(address).strip()
            fields_to_update.append("address")
        if tax_number and not best_match.tax_number:
            best_match.tax_number = str(tax_number).strip()
            fields_to_update.append("tax_number")
        if fields_to_update:
            best_match.save(update_fields=fields_to_update)
        return best_match

    # 3. Create new party
    return Party.objects.create(
        name=clean_name,
        phone=str(phone).strip() if phone else "",
        party_type=party_type,
        urdu_name=urdu_name,
        email=email,
        address=address,
        tax_number=tax_number,
        notes=notes,
        **kwargs,
    )
