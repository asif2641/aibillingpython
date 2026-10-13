"""
compile_mo.py - Pure Python PO to MO compiler.
"""

import ast
import re
import struct
from pathlib import Path


def parse_po(po_path: Path):
    content = po_path.read_text(encoding="utf-8")
    entries = []

    # Split into message blocks separated by blank lines
    blocks = re.split(r"\n\s*\n", content)

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        msgid_parts = []
        msgstr_parts = []
        current_part = None

        for line in lines:
            if line.startswith("#"):
                continue
            if line.startswith("msgid "):
                current_part = "msgid"
                raw = line[len("msgid ") :].strip()
                msgid_parts.append(ast.literal_eval(raw))
            elif line.startswith("msgstr "):
                current_part = "msgstr"
                raw = line[len("msgstr ") :].strip()
                msgstr_parts.append(ast.literal_eval(raw))
            elif line.startswith('"') and line.endswith('"'):
                if current_part == "msgid":
                    msgid_parts.append(ast.literal_eval(line))
                elif current_part == "msgstr":
                    msgstr_parts.append(ast.literal_eval(line))

        if msgid_parts and msgstr_parts is not None:
            msgid = "".join(msgid_parts)
            msgstr = "".join(msgstr_parts)
            entries.append((msgid, msgstr))

    return entries


def write_mo(entries, mo_path: Path):
    # Sort entries by msgid (GNU gettext standard)
    entries.sort(key=lambda item: item[0].encode("utf-8"))

    count = len(entries)
    orig_table = []
    trans_table = []

    orig_bytes = bytearray()
    trans_bytes = bytearray()

    # Offsets table
    orig_table_offset = 28
    trans_table_offset = 28 + count * 8
    strings_offset = trans_table_offset + count * 8

    cur_offset = strings_offset
    for orig, _ in entries:
        b = orig.encode("utf-8") + b"\x00"
        orig_table.append((len(b) - 1, cur_offset))
        orig_bytes.extend(b)
        cur_offset += len(b)

    for _, trans in entries:
        b = trans.encode("utf-8") + b"\x00"
        trans_table.append((len(b) - 1, cur_offset))
        trans_bytes.extend(b)
        cur_offset += len(b)

    header = struct.pack(
        "<Iiiiiii",
        0x950412DE,  # Magic number
        0,  # Format version
        count,  # Number of strings
        orig_table_offset,
        trans_table_offset,
        0,  # Hashing table size
        0,  # Hashing table offset
    )

    mo_data = bytearray(header)
    for length, offset in orig_table:
        mo_data.extend(struct.pack("<ii", length, offset))
    for length, offset in trans_table:
        mo_data.extend(struct.pack("<ii", length, offset))
    mo_data.extend(orig_bytes)
    mo_data.extend(trans_bytes)

    mo_path.write_bytes(mo_data)
    print(f"Successfully compiled {count} entries to {mo_path}")


if __name__ == "__main__":
    po_file = Path("locale/ur/LC_MESSAGES/django.po")
    mo_file = Path("locale/ur/LC_MESSAGES/django.mo")
    parsed = parse_po(po_file)
    write_mo(parsed, mo_file)
