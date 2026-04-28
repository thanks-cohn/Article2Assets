#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


SCHEMA_VERSION = "0.1.0"
TOOL_NAME = "fm_export_training_jsonl"
TOOL_VERSION = "0.1.0"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def text_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def export_status(file_rec, min_text_chars):
    active = file_rec.get("active_view", {})
    text_obj = active.get("text", {})
    text = text_obj.get("plain", "") if isinstance(text_obj, dict) else ""
    blocks = active.get("blocks", [])
    urls = active.get("urls", [])

    reasons = []

    if len(text.strip()) < min_text_chars:
        reasons.append("text_below_min_chars")

    if not isinstance(blocks, list) or len(blocks) == 0:
        reasons.append("no_ocr_blocks")

    if reasons:
        return "review", reasons

    return "ready", []


def main():
    parser = argparse.ArgumentParser(
        description="Export FileMonster union data into ML-ready training JSONL."
    )

    parser.add_argument("--union", required=True, help="filemonster_layer_union.json")
    parser.add_argument("--output-jsonl", required=True, help="Output training JSONL")
    parser.add_argument("--output-json", default=None, help="Optional export summary JSON")
    parser.add_argument("--min-text-chars", type=int, default=1, help="Minimum text chars for ready status")
    parser.add_argument("--include-blocks", action="store_true", help="Include OCR blocks")
    parser.add_argument("--include-urls", action="store_true", help="Include URLs")
    parser.add_argument("--ready-only", action="store_true", help="Only export rows with export_status=ready")

    args = parser.parse_args()

    union_path = Path(args.union).expanduser().resolve()
    union = read_json(union_path)

    rows = []
    skipped_review = 0
    ready_count = 0
    review_count = 0

    for file_rec in union.get("files", []):
        active = file_rec.get("active_view", {})
        base = file_rec.get("base", {})

        text_obj = active.get("text", {})
        text = text_obj.get("plain", "") if isinstance(text_obj, dict) else ""
        lines = text_lines(text)

        urls = active.get("urls", [])
        blocks = active.get("blocks", [])
        source_layers = active.get("layer_ids_used", [])

        status, reasons = export_status(file_rec, args.min_text_chars)

        if status == "ready":
            ready_count += 1
        else:
            review_count += 1

        if args.ready_only and status != "ready":
            skipped_review += 1
            continue

        row = {
            "schema": {
                "name": "FMIAF-training-export",
                "version": SCHEMA_VERSION
            },
            "record_type": "training_export_entry",
            "created_utc": now_utc(),

            "fm_id": file_rec.get("fm_id"),
            "ff_id": file_rec.get("ff_id"),
            "file": file_rec.get("file"),
            "sha256": base.get("sha256"),
            "media_type": base.get("media_type"),
            "format": base.get("format"),
            "width": base.get("width"),
            "height": base.get("height"),
            "size_bytes": base.get("size_bytes"),

            "text": text,
            "text_lines": lines,
            "text_chars": len(text),
            "text_line_count": len(lines),

            "url_count": len(urls) if isinstance(urls, list) else 0,
            "ocr_block_count": len(blocks) if isinstance(blocks, list) else 0,

            "source_layers": source_layers,
            "text_sources": text_obj.get("sources", []) if isinstance(text_obj, dict) else [],

            "export_status": status,
            "review_reasons": reasons,

            "provenance": {
                "source_union": str(union_path),
                "union_run_id": union.get("union_run_id"),
                "tool_name": TOOL_NAME,
                "tool_version": TOOL_VERSION
            }
        }

        if args.include_urls:
            row["urls"] = urls if isinstance(urls, list) else []

        if args.include_blocks:
            row["ocr_blocks"] = blocks if isinstance(blocks, list) else []

        rows.append(row)

    write_jsonl(args.output_jsonl, rows)

    summary = {
        "schema": {
            "name": "FMIAF-training-export-summary",
            "version": SCHEMA_VERSION
        },
        "record_type": "training_export_summary",
        "created_utc": now_utc(),
        "source_union": str(union_path),
        "union_run_id": union.get("union_run_id"),
        "rows_written": len(rows),
        "ready_count": ready_count,
        "review_count": review_count,
        "skipped_review": skipped_review,
        "min_text_chars": args.min_text_chars,
        "include_urls": bool(args.include_urls),
        "include_blocks": bool(args.include_blocks),
        "ready_only": bool(args.ready_only),
        "output_jsonl": str(Path(args.output_jsonl).expanduser().resolve()),
        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION
        }
    }

    if args.output_json:
        write_json(args.output_json, summary)

    print("Training export complete.")
    print(f"Rows written:     {len(rows)}")
    print(f"Ready rows:       {ready_count}")
    print(f"Review rows:      {review_count}")
    print(f"Skipped review:   {skipped_review}")
    print(f"JSONL:            {args.output_jsonl}")
    if args.output_json:
        print(f"Summary JSON:     {args.output_json}")


if __name__ == "__main__":
    main()
