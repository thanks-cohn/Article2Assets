#!/usr/bin/env python3

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from datetime import datetime, timezone

import fitz


SCHEMA_VERSION = "0.1.0"
TOOL_NAME = "fm_spatial_text_module"
TOOL_VERSION = "0.1.0"

URL_RE = re.compile(r"(https?://[^\s<>'\"\)\]]+|www\.[^\s<>'\"\)\]]+)", re.I)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def make_run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def clean_url(url):
    url = url.strip().rstrip(".,;:!?)]}\"'…")
    if url.lower().startswith("www."):
        url = "https://" + url
    return url


def rect_to_list(rect):
    return [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]


def word_from_tuple(w, page_no, index):
    x0, y0, x1, y1, text, block_no, line_no, word_no = w[:8]
    return {
        "id": f"P{page_no}_W{index}",
        "page": page_no,
        "text": text,
        "bbox": [float(x0), float(y0), float(x1), float(y1)],
        "block_no": int(block_no),
        "line_no": int(line_no),
        "word_no": int(word_no)
    }


def extract_pdf_spatial(pdf_path, granularity):
    doc = fitz.open(pdf_path)
    pages = []

    all_text = []
    all_urls = []

    for page_index, page in enumerate(doc, start=1):
        width = float(page.rect.width)
        height = float(page.rect.height)

        words_raw = page.get_text("words")
        words = [word_from_tuple(w, page_index, i + 1) for i, w in enumerate(words_raw)]

        blocks = []
        lines = []

        text_dict = page.get_text("dict")

        block_i = 0
        line_i = 0

        for b in text_dict.get("blocks", []):
            if b.get("type") != 0:
                continue

            block_i += 1
            block_text_parts = []
            block_bbox = b.get("bbox")

            for ln in b.get("lines", []):
                line_i += 1
                spans = ln.get("spans", [])
                line_text = "".join(span.get("text", "") for span in spans).strip()
                if not line_text:
                    continue

                line_bbox = ln.get("bbox")
                line_obj = {
                    "id": f"P{page_index}_L{line_i}",
                    "page": page_index,
                    "text": line_text,
                    "bbox": [float(v) for v in line_bbox],
                    "block_no": block_i
                }
                lines.append(line_obj)
                block_text_parts.append(line_text)
                all_text.append(line_text)

                for m in URL_RE.finditer(line_text):
                    all_urls.append({
                        "url": clean_url(m.group(0)),
                        "text": m.group(0),
                        "bbox": line_obj["bbox"],
                        "page": page_index,
                        "source_object_id": line_obj["id"],
                        "bbox_policy": "pdf_native_line_bbox_contains_url"
                    })

            block_text = "\n".join(block_text_parts).strip()
            if block_text:
                blocks.append({
                    "id": f"P{page_index}_B{block_i}",
                    "page": page_index,
                    "text": block_text,
                    "bbox": [float(v) for v in block_bbox],
                    "line_count": len(block_text_parts)
                })

        if granularity == "word":
            objects = words
        elif granularity == "block":
            objects = blocks
        elif granularity == "both":
            objects = lines + words
        else:
            objects = lines

        pages.append({
            "page": page_index,
            "width": width,
            "height": height,
            "blocks": blocks,
            "lines": lines,
            "words": words,
            "objects": objects,
            "text_chars": sum(len(x.get("text", "")) for x in objects),
            "object_count": len(objects)
        })

    doc.close()

    return {
        "pages": pages,
        "plain_text": "\n".join(all_text).strip(),
        "urls": all_urls
    }


def svg_for_page(page, granularity, show_boxes):
    width = page["width"]
    height = page["height"]

    if granularity == "word":
        objects = page["words"]
    elif granularity == "block":
        objects = page["blocks"]
    elif granularity == "both":
        objects = page["lines"] + page["words"]
    else:
        objects = page["lines"]

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    parts.append('<rect x="0" y="0" width="100%" height="100%" fill="white"/>')

    for obj in objects:
        x0, y0, x1, y1 = obj["bbox"]
        text = html.escape(obj.get("text", ""))
        obj_id = html.escape(obj.get("id", ""))

        if show_boxes:
            parts.append(
                f'<rect id="{obj_id}_box" x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" '
                f'fill="none" stroke="black" stroke-width="0.5" opacity="0.45"/>'
            )

        font_size = max(4, (y1 - y0) * 0.75)
        parts.append(
            f'<text id="{obj_id}" x="{x0}" y="{y1}" font-family="Arial, sans-serif" '
            f'font-size="{font_size}" fill="black">{text}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def write_svg_bundle(module_dir, stem, run_id, pages, granularity, show_boxes):
    svg_paths = []

    for page in pages:
        svg_name = f"spatial_text.{run_id}.p{page['page']:04d}.{granularity}.svg"
        svg_path = module_dir / svg_name
        svg_path.write_text(svg_for_page(page, granularity, show_boxes), encoding="utf-8")
        svg_paths.append(svg_path.name)

    return svg_paths


def main():
    parser = argparse.ArgumentParser(
        description="FileMonster spatial text module: PDF-native text coordinates to SVG + JSON."
    )

    parser.add_argument("--master", required=True)
    parser.add_argument("--module-index", default=None)
    parser.add_argument("--granularity", default="line", choices=["line", "word", "block", "both"])
    parser.add_argument("--show-boxes", action="store_true")
    parser.add_argument("--run-id", default=None)

    args = parser.parse_args()

    run_id = args.run_id or make_run_id()

    master_path = Path(args.master).expanduser().resolve()
    master = read_json(master_path)
    root = Path(master["root_path_at_scan"]).expanduser().resolve()

    module_index = (
        Path(args.module_index).expanduser().resolve()
        if args.module_index
        else master_path.parent / "filemonster_module_index.jsonl"
    )

    pdfs = [
        f for f in master.get("files", [])
        if f.get("format") == "pdf" or str(f.get("path", "")).lower().endswith(".pdf")
    ]

    processed = 0
    failed = 0

    for rec in pdfs:
        rel = rec["path"]
        pdf_path = root / rel
        module_dir_rel = rec.get("module_output_directory", rel + ".fm.modules")
        module_dir = root / module_dir_rel
        module_dir.mkdir(parents=True, exist_ok=True)

        print(f"[PDF] {pdf_path}")

        try:
            spatial = extract_pdf_spatial(pdf_path, args.granularity)
            svg_names = write_svg_bundle(
                module_dir,
                Path(rel).stem,
                run_id,
                spatial["pages"],
                args.granularity,
                args.show_boxes
            )

            source_sha = sha256_file(pdf_path)
            module_name = f"spatial_text.{run_id}.json"
            module_path = module_dir / module_name
            module_rel = str(Path(module_dir_rel) / module_name)

            module_json = {
                "schema": {"name": "FMIAF-module", "version": SCHEMA_VERSION},
                "record_type": "module_output",
                "module": {
                    "name": "spatial_text",
                    "version": TOOL_VERSION,
                    "engine": "pymupdf_pdf_native",
                    "run_id": run_id,
                    "created_utc": now_utc(),
                    "append_only": True
                },
                "target": {
                    "fm_id": rec["fm_id"],
                    "ff_id": rec["ff_id"],
                    "file_path": rel,
                    "source_sha256": source_sha
                },
                "placement": {
                    "suggested_target": "modules.spatial_text",
                    "merge_strategy": "pointer_append",
                    "overwrite_originals": False
                },
                "data": {
                    "success": True,
                    "source": "pdf_native",
                    "granularity": args.granularity,
                    "svg_pages": svg_names,
                    "text": {
                        "plain": spatial["plain_text"]
                    },
                    "urls": spatial["urls"],
                    "pages": spatial["pages"],
                    "blocks": [
                        b
                        for p in spatial["pages"]
                        for b in p["blocks"]
                    ],
                    "regions": [
                        {
                            "region_id": obj["id"],
                            "page": obj["page"],
                            "bbox": obj["bbox"],
                            "label": "spatial_text_object",
                            "text": obj["text"],
                            "granularity": args.granularity
                        }
                        for p in spatial["pages"]
                        for obj in p["objects"]
                    ]
                },
                "provenance": {
                    "tool_name": TOOL_NAME,
                    "tool_version": TOOL_VERSION,
                    "created_utc": now_utc()
                }
            }

            write_json(module_path, module_json)

            append_jsonl(module_index, {
                "schema_version": SCHEMA_VERSION,
                "record_type": "module_index_entry",
                "created_utc": now_utc(),
                "fm_id": rec["fm_id"],
                "ff_id": rec["ff_id"],
                "file": rel,
                "module_name": "spatial_text",
                "module_json": module_rel,
                "suggested_target": "modules.spatial_text",
                "merge_strategy": "pointer_append",
                "run_id": run_id,
                "append_only": True,
                "source_sha256": source_sha,
                "tool_name": TOOL_NAME,
                "tool_version": TOOL_VERSION
            })

            processed += 1
            print(f"  module: {module_rel}")
            print(f"  pages:  {len(spatial['pages'])}")
            print(f"  svgs:   {len(svg_names)}")
            print(f"  urls:   {len(spatial['urls'])}")

        except Exception as e:
            failed += 1
            print(f"  ERROR: {e}")

    print()
    print("Spatial text module complete.")
    print(f"Run ID:      {run_id}")
    print(f"PDFs found:  {len(pdfs)}")
    print(f"Processed:   {processed}")
    print(f"Failed:      {failed}")
    print(f"Module index:{module_index}")


if __name__ == "__main__":
    main()
