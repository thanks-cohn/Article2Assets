#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from collections import defaultdict


REQUIRED_TOP_LEVEL = [
    "schema",
    "record_type",
    "module",
    "target",
    "placement",
    "data"
]

REQUIRED_MODULE_FIELDS = [
    "name",
    "version",
    "created_utc"
]

REQUIRED_TARGET_FIELDS = [
    "fm_id",
    "ff_id"
]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    rows = []
    path = Path(path)

    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                rows.append(json.loads(line))
            except Exception as e:
                rows.append({
                    "_bad_json_line": line_no,
                    "_error": str(e),
                    "_raw": line
                })

    return rows


def validate_module_json(path):
    errors = []
    warnings = []

    try:
        data = read_json(path)
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Unreadable JSON: {e}"],
            "warnings": [],
            "summary": {}
        }

    for field in REQUIRED_TOP_LEVEL:
        if field not in data:
            errors.append(f"Missing top-level field: {field}")

    module = data.get("module", {})
    target = data.get("target", {})
    payload = data.get("data", {})

    for field in REQUIRED_MODULE_FIELDS:
        if field not in module:
            errors.append(f"Missing module field: module.{field}")

    for field in REQUIRED_TARGET_FIELDS:
        if field not in target:
            errors.append(f"Missing target field: target.{field}")

    if not isinstance(payload, dict):
        errors.append("data must be object/dict")

    if "urls" in payload and not isinstance(payload["urls"], list):
        errors.append("data.urls must be list")

    if "blocks" in payload and not isinstance(payload["blocks"], list):
        errors.append("data.blocks must be list")

    if "text" in payload:
        if not isinstance(payload["text"], dict):
            errors.append("data.text must be object/dict")
        elif "plain" not in payload["text"]:
            warnings.append("data.text exists but missing text.plain")

    summary = {
        "module_name": module.get("name"),
        "module_version": module.get("version"),
        "fm_id": target.get("fm_id"),
        "ff_id": target.get("ff_id"),
        "url_count": len(payload.get("urls", [])) if isinstance(payload.get("urls"), list) else 0,
        "block_count": len(payload.get("blocks", [])) if isinstance(payload.get("blocks"), list) else 0,
        "text_chars": len(payload.get("text", {}).get("plain", "")) if isinstance(payload.get("text"), dict) else 0
    }

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": summary
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate FileMonster module JSON blocks."
    )

    parser.add_argument("--master", required=True, help="FileMonster master JSON")
    parser.add_argument("--module-index", default=None, help="Optional explicit module index path")
    parser.add_argument("--output", default=None, help="Optional validation report JSON")

    args = parser.parse_args()

    master_path = Path(args.master).expanduser().resolve()
    master = read_json(master_path)

    root = Path(master["root_path_at_scan"]).expanduser().resolve()

    if args.module_index:
        module_index_path = Path(args.module_index).expanduser().resolve()
    else:
        module_index_path = master_path.parent / "filemonster_module_index.jsonl"

    entries = read_jsonl(module_index_path)

    results = []
    total_valid = 0
    total_invalid = 0
    total_warnings = 0

    for entry in entries:
        if "_bad_json_line" in entry:
            results.append({
                "module_json": None,
                "valid": False,
                "errors": [f"Bad module index JSONL line {entry['_bad_json_line']}: {entry['_error']}"],
                "warnings": []
            })
            total_invalid += 1
            continue

        rel_module = entry.get("module_json")
        if not rel_module:
            results.append({
                "module_json": None,
                "valid": False,
                "errors": ["Missing module_json in index entry"],
                "warnings": []
            })
            total_invalid += 1
            continue

        abs_module = root / rel_module

        if not abs_module.exists():
            results.append({
                "module_json": rel_module,
                "valid": False,
                "errors": ["Module JSON file missing"],
                "warnings": []
            })
            total_invalid += 1
            continue

        validation = validate_module_json(abs_module)

        results.append({
            "module_json": rel_module,
            **validation
        })

        if validation["valid"]:
            total_valid += 1
        else:
            total_invalid += 1

        total_warnings += len(validation["warnings"])

    report = {
        "schema": {
            "name": "FMIAF-module-validation",
            "version": "0.1.0"
        },
        "record_type": "module_validation_report",
        "master": str(master_path),
        "module_index": str(module_index_path),
        "summary": {
            "entries_checked": len(results),
            "valid": total_valid,
            "invalid": total_invalid,
            "warnings": total_warnings
        },
        "results": results
    }

    if args.output:
        Path(args.output).write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    print("Validation complete.")
    print(f"Entries checked: {len(results)}")
    print(f"Valid:           {total_valid}")
    print(f"Invalid:         {total_invalid}")
    print(f"Warnings:        {total_warnings}")

    if args.output:
        print(f"Report saved:    {args.output}")


if __name__ == "__main__":
    main()
