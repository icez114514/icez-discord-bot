"""Exact, offline conversion of legacy crystal and bank snapshots."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

MAX_ID = 2**64 - 1


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key; conversion stopped.")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Non-finite JSON number; conversion stopped.")


def load_exact(path: Path):
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"), parse_float=Decimal,
                          object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Cannot read a valid UTF-8 JSON source.") from None
    return data, hashlib.sha256(raw).hexdigest()


def user_id(value) -> int:
    if type(value) is not str or not value.isascii() or not value.isdecimal():
        raise ValueError("User IDs must be decimal strings.")
    number = int(value)
    if not 0 < number <= MAX_ID:
        raise ValueError("User ID is outside the Discord ID range.")
    return number


def legacy_integer(value) -> int:
    if type(value) is int:
        return value
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    raise ValueError("Legacy amounts must be finite whole numbers.")


def normalized_source(data, field):
    if not isinstance(data, dict):
        raise ValueError("Legacy source must be an object keyed by user ID.")
    result = {}
    for key, record in data.items():
        uid = user_id(key)
        if uid in result:
            raise ValueError("Duplicate normalized user ID.")
        if not isinstance(record, dict) or field not in record:
            raise ValueError("Legacy record is missing its amount field.")
        result[uid] = legacy_integer(record[field])
    return result


def merge_data(crystals, bank):
    cash = normalized_source(crystals, "crystals")
    savings = normalized_source(bank, "savings")
    selected = set(cash) | {uid for uid, value in savings.items() if value > 0}
    rows, corrections = [], []
    total = zero = huge = 0
    for uid in sorted(selected):
        original_cash, original_savings = cash.get(uid, 0), savings.get(uid, 0)
        balance = max(original_cash, 0) + max(original_savings, 0)
        rows.append({"user_id": str(uid), "balance": str(balance)})
        total += balance
        zero += balance == 0
        huge += balance > 2**63 - 1
    # Include corrections for excluded negative-only bank records too.
    for uid in sorted(set(cash) | set(savings)):
        if cash.get(uid, 0) < 0 or savings.get(uid, 0) < 0:
            corrections.append({
                "user_id": str(uid), "original_crystals": str(cash.get(uid, 0)),
                "original_savings": str(savings.get(uid, 0)), "included": uid in selected,
                "balance": str(max(cash.get(uid, 0), 0) + max(savings.get(uid, 0), 0)),
            })
    return rows, {
        "accounts": len(rows), "skipped": len(set(cash) | set(savings)) - len(rows),
        "total": str(total), "zero_accounts": zero, "over_bigint": huge,
        "negative_corrections": corrections,
    }


def merge_files(crystals: Path, bank: Path, output: Path) -> dict:
    report_path = output.with_name(output.name + ".report.json")
    if output.resolve() in (crystals.resolve(), bank.resolve()) or report_path.resolve() in (
        crystals.resolve(), bank.resolve()
    ):
        raise ValueError("Output must not overwrite either source.")
    if output.exists() or report_path.exists():
        raise ValueError("Output or report already exists; choose a new output path.")
    cash, cash_hash = load_exact(crystals)
    deposits, bank_hash = load_exact(bank)
    rows, report = merge_data(cash, deposits)
    payload = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    report["sources"] = {
        "crystals": {"file": crystals.name, "sha256": cash_hash},
        "bank": {"file": bank.name, "sha256": bank_hash},
    }
    report["output_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    with report_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report
