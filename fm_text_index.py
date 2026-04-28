#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Build a clean text index from FileMonster layer union JSON."
    )

    parser.add_argument("--union", required=True, help="filemonster_layer_union.json")
    parser.add_argument("--output-jsonl", required=True, help="Output text index JSONL")
    parser.add_argument("--output-json", default=None, help="Optional summary JSON")
    parser.add_argument("--min-chars", type=int, default=1, help="Skip records with less text than this")
    parser.add_argument("--dedupe", action="store_true", help="Deduplicate identical text per file")

    args = parser.parse_args()

    union_path = Path(args.union).expanduser().resolve()
    union = read_json(union_path)

    rows = []
    seen = set()

    for file_rec in union.get("files", []):
        fm_id = file_rec.get("fm_id")
        ff_id = file_rec.get("ff_id")
        file_path = file_rec.get("file")

        active_view = file_rec.get("active_view", {})
        text_obj = active_view.get("text", {})
        plain = text_obj.get("plain", "") if isinstance(text_obj, dict) else ""

        plain = plain.strip()
        if len(plain) < args.min_chars:
            continue

        key = (fm_id, plain)
        if args.dedupe and key in seen:
            continue
        seen.add(key)

        sources = text_obj.get("sources", []) if isinstance(text_obj, dict) else []

        rows.append({
            "record_type": "text_index_entry",
            "created_utc": now_utc(),
            "fm_id": fm_id,
            "ff_id": ff_id,
            "file": file_path,
            "text_chars": len(plain),
            "text_lines": len([line for line in plain.splitlines() if line.strip()]),
            "text": plain,
            "sources": sources
        })

    write_jsonl(args.output_jsonl, rows)

    summary = {
        "schema": {"name": "FMIAF-text-index", "version": "0.1.0"},
        "record_type": "text_index_summary",
        "created_utc": now_utc(),
        "source_union": str(union_path),
        "text_entries": len(rows),
        "dedupe": bool(args.dedupe),
        "min_chars": args.min_chars,
        "output_jsonl": str(Path(args.output_jsonl).expanduser().resolve())
    }

    if args.output_json:
        write_json(args.output_json, summary)

    print("Text index complete.")
    print(f"Text records written: {len(rows)}")
    print(f"JSONL:                {args.output_jsonl}")
    if args.output_json:
        print(f"Summary JSON:         {args.output_json}")


if __name__ == "__main__":
    main()
