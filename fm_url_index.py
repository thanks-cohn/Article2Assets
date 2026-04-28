#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


SCHEMA_VERSION = "0.2.0"
TOOL_NAME = "fm_url_index"
TOOL_VERSION = "0.2.0"

TRAILING_JUNK = ".,;:!?)]}\"'…"


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


def normalize_url(url):
    if not url:
        return None

    url = str(url).strip().rstrip(TRAILING_JUNK)

    if url.lower().startswith("www."):
        url = "https://" + url

    parsed = urlparse(url)

    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    if netloc.startswith("www."):
        canonical_netloc = netloc[4:]
    else:
        canonical_netloc = netloc

    path = parsed.path or ""

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_pairs = [
        (k, v)
        for k, v in query_pairs
        if not k.lower().startswith("utm_")
    ]
    query = urlencode(query_pairs, doseq=True)

    canonical = urlunparse((
        scheme,
        canonical_netloc,
        path,
        "",
        query,
        ""
    ))

    display = urlunparse((
        scheme,
        netloc,
        path,
        "",
        query,
        ""
    ))

    return {
        "url": display,
        "canonical_url": canonical,
        "domain": canonical_netloc,
        "scheme": scheme
    }


def source_value(u, key):
    return u.get(key) or u.get("_" + key)


def main():
    parser = argparse.ArgumentParser(
        description="Build a clean URL index from FileMonster layer union JSON."
    )

    parser.add_argument("--union", required=True, help="filemonster_layer_union.json")
    parser.add_argument("--output-jsonl", required=True, help="Output URL index JSONL")
    parser.add_argument("--output-json", default=None, help="Optional summary JSON")
    parser.add_argument("--dedupe", action="store_true", help="Deduplicate identical canonical URLs per file")
    parser.add_argument("--global-dedupe", action="store_true", help="Deduplicate identical canonical URLs globally")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="Skip URL rows below this confidence")

    args = parser.parse_args()

    union_path = Path(args.union).expanduser().resolve()
    union = read_json(union_path)

    rows = []
    seen = set()
    skipped_bad_url = 0
    skipped_low_conf = 0

    for file_rec in union.get("files", []):
        fm_id = file_rec.get("fm_id")
        ff_id = file_rec.get("ff_id")
        file_path = file_rec.get("file")
        base = file_rec.get("base", {})

        urls = file_rec.get("active_view", {}).get("urls", [])

        for i, u in enumerate(urls, start=1):
            raw_url = u.get("url") if isinstance(u, dict) else None
            normalized = normalize_url(raw_url)

            if not normalized or not normalized.get("canonical_url"):
                skipped_bad_url += 1
                continue

            confidence = u.get("confidence")
            if confidence is not None:
                try:
                    confidence = float(confidence)
                except Exception:
                    confidence = None

            if confidence is not None and confidence < args.min_confidence:
                skipped_low_conf += 1
                continue

            if args.global_dedupe:
                key = normalized["canonical_url"]
            else:
                key = (fm_id, normalized["canonical_url"])

            if args.dedupe and key in seen:
                continue

            seen.add(key)

            rows.append({
                "schema": {"name": "FMIAF-url-index", "version": SCHEMA_VERSION},
                "record_type": "url_index_entry",
                "created_utc": now_utc(),

                "fm_id": fm_id,
                "ff_id": ff_id,
                "file": file_path,
                "sha256": base.get("sha256"),
                "media_type": base.get("media_type"),
                "format": base.get("format"),

                "url_index": i,
                "url": normalized["url"],
                "canonical_url": normalized["canonical_url"],
                "domain": normalized["domain"],
                "scheme": normalized["scheme"],

                "ocr_text": u.get("text"),
                "bbox": u.get("bbox"),
                "confidence": confidence,
                "source_block_id": u.get("source_block_id"),

                "source_layer": source_value(u, "source_layer"),
                "source_module": source_value(u, "source_module"),
                "source_run_id": source_value(u, "source_run_id"),

                "bbox_policy": u.get("bbox_policy"),
                "provenance": {
                    "source_union": str(union_path),
                    "union_run_id": union.get("union_run_id"),
                    "tool_name": TOOL_NAME,
                    "tool_version": TOOL_VERSION
                }
            })

    write_jsonl(args.output_jsonl, rows)

    summary = {
        "schema": {"name": "FMIAF-url-index-summary", "version": SCHEMA_VERSION},
        "record_type": "url_index_summary",
        "created_utc": now_utc(),
        "source_union": str(union_path),
        "union_run_id": union.get("union_run_id"),
        "url_entries": len(rows),
        "dedupe": bool(args.dedupe),
        "global_dedupe": bool(args.global_dedupe),
        "min_confidence": args.min_confidence,
        "skipped_bad_url": skipped_bad_url,
        "skipped_low_confidence": skipped_low_conf,
        "output_jsonl": str(Path(args.output_jsonl).expanduser().resolve()),
        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION
        }
    }

    if args.output_json:
        write_json(args.output_json, summary)

    print("URL index complete.")
    print(f"URLs written:           {len(rows)}")
    print(f"Skipped bad URLs:       {skipped_bad_url}")
    print(f"Skipped low confidence: {skipped_low_conf}")
    print(f"JSONL:                  {args.output_jsonl}")
    if args.output_json:
        print(f"Summary JSON:           {args.output_json}")


if __name__ == "__main__":
    main()
