#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import fitz
from PIL import Image
from paddleocr import PaddleOCR


SCHEMA_VERSION = "0.3.0"
TOOL_NAME = "paddle_ocr_full_module"
TOOL_VERSION = "0.3.0"

URL_RE = re.compile(
    r"(https?://[^\s<>'\"\)\]]+|www\.[^\s<>'\"\)\]]+)",
    re.IGNORECASE
)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def make_run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def timestamp_path(path, run_id):
    path = Path(path).expanduser()
    suffix = path.suffix
    if not suffix:
        return path.with_name(path.name + f".{run_id}")
    stem = path.name[:-len(suffix)]
    return path.with_name(f"{stem}.{run_id}{suffix}")


def clean_url(url):
    url = url.strip().rstrip(".,;:!?)]}")
    if url.lower().startswith("www."):
        url = "https://" + url
    return url


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def rel_to_root(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except Exception:
        return str(path)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_ocr_engine(lang):
    return PaddleOCR(
        lang=lang,
        use_textline_orientation=True,
    )


def run_ocr(ocr_engine, image_path, min_confidence):
    result = ocr_engine.predict(str(image_path))
    blocks = []

    for page_result in result:
        texts = page_result.get("rec_texts", [])
        scores = page_result.get("rec_scores", [])
        boxes = page_result.get("rec_boxes")
        polys = page_result.get("rec_polys")

        for i, text in enumerate(texts):
            text = str(text).strip()
            if not text:
                continue

            conf = float(scores[i]) if i < len(scores) else 1.0
            if conf < min_confidence:
                continue

            if boxes is not None and i < len(boxes):
                x0, y0, x1, y1 = map(float, boxes[i])
            elif polys is not None and i < len(polys):
                xs = [float(p[0]) for p in polys[i]]
                ys = [float(p[1]) for p in polys[i]]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            else:
                continue

            blocks.append({
                "block_id": f"OCRB{len(blocks) + 1}",
                "text": text,
                "confidence": conf,
                "bbox": [x0, y0, x1, y1],
                "bbox_type": "ocr_textline_or_block"
            })

    return blocks


def extract_urls(blocks):
    urls = []

    for block in blocks:
        for match in URL_RE.finditer(block["text"]):
            raw = match.group(0)
            urls.append({
                "url": clean_url(raw),
                "text": raw,
                "bbox": block["bbox"],
                "confidence": block["confidence"],
                "source_block_id": block["block_id"],
                "bbox_policy": "anchor_zone_contains_url_not_exact"
            })

    return urls


def inflate_bbox(bbox, pad, width, height):
    x0, y0, x1, y1 = bbox
    return [
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(width, x1 + pad),
        min(height, y1 + pad),
    ]


def insert_text_layer(page, blocks, visible=False):
    for b in blocks:
        x0, y0, x1, y1 = b["bbox"]
        rect = fitz.Rect(x0, y0, x1, y1)
        height = max(1, y1 - y0)
        fontsize = max(4, height * 0.75)

        page.insert_textbox(
            rect,
            b["text"],
            fontsize=fontsize,
            fontname="helv",
            render_mode=0 if visible else 3,
            color=(1, 0, 0) if visible else (0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
        )


def add_clickable_links(page, urls, width, height, pad):
    for u in urls:
        bbox = inflate_bbox(u["bbox"], pad=pad, width=width, height=height)
        page.insert_link({
            "kind": fitz.LINK_URI,
            "from": fitz.Rect(*bbox),
            "uri": u["url"],
        })


def append_module_index(module_index, entry):
    module_index.parent.mkdir(parents=True, exist_ok=True)
    with module_index.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    started = time.time()

    parser = argparse.ArgumentParser(
        description="FileMonster PaddleOCR full module: timestamped OCR modules, clickable PDF, research JSON, text, URL extraction."
    )

    parser.add_argument("--master", required=True, help="FileMonster master JSON")
    parser.add_argument("--lang", default="en", help="PaddleOCR language, e.g. en, ru, uk")
    parser.add_argument("--output-pdf", required=True, help="Clickable searchable OCR PDF base output")
    parser.add_argument("--output-json", required=True, help="Research OCR JSON base output")
    parser.add_argument("--module-index", default=None, help="Defaults beside master as filemonster_module_index.jsonl")
    parser.add_argument("--visible-text", action="store_true", help="Debug: show OCR text visibly over image")
    parser.add_argument("--link-pad", type=float, default=18.0, help="Clickable URL bbox padding in pixels")
    parser.add_argument("--min-confidence", type=float, default=0.20, help="Minimum OCR confidence")
    parser.add_argument("--run-id", default=None, help="Optional fixed run id. Default: UTC timestamp")
    parser.add_argument("--no-timestamp-big-outputs", action="store_true", help="Do not timestamp PDF/research JSON")
    parser.add_argument("--latest-link", action="store_true", help="Also write/update non-timestamped latest PDF/research JSON paths")

    args = parser.parse_args()

    run_id = args.run_id or make_run_id()

    master_path = Path(args.master).expanduser().resolve()
    master = read_json(master_path)
    root = Path(master["root_path_at_scan"]).expanduser().resolve()

    output_pdf_base = Path(args.output_pdf).expanduser().resolve()
    output_json_base = Path(args.output_json).expanduser().resolve()

    if args.no_timestamp_big_outputs:
        output_pdf = output_pdf_base
        output_json = output_json_base
    else:
        output_pdf = timestamp_path(output_pdf_base, run_id).resolve()
        output_json = timestamp_path(output_json_base, run_id).resolve()

    if args.module_index:
        module_index = Path(args.module_index).expanduser().resolve()
    else:
        module_index = master_path.parent / "filemonster_module_index.jsonl"

    ocr_engine = make_ocr_engine(args.lang)
    pdf_doc = fitz.open()

    files = [
        f for f in master.get("files", [])
        if f.get("media_type") == "image"
    ]

    research = {
        "schema": {"name": "FMIAF-OCR-Research", "version": SCHEMA_VERSION},
        "record_type": "ocr_research_bundle",
        "created_utc": now_utc(),
        "run_id": run_id,
        "append_only": True,
        "master": rel_to_root(master_path, root),
        "module_index": rel_to_root(module_index, root),
        "output_pdf": rel_to_root(output_pdf, root),
        "output_json": rel_to_root(output_json, root),
        "tool": {
            "name": TOOL_NAME,
            "version": TOOL_VERSION
        },
        "engine": {
            "name": "PaddleOCR",
            "language": args.lang,
            "min_confidence": args.min_confidence
        },
        "bbox_policy": {
            "ocr_boxes": "textline_or_block_boxes_from_engine",
            "url_boxes": "anchor_zone_contains_url_not_exact",
            "clickable_link_padding_px": args.link_pad
        },
        "summary": {
            "files_total": len(files),
            "files_processed": 0,
            "files_failed": 0,
            "total_blocks": 0,
            "total_urls": 0,
            "total_text_chars": 0
        },
        "pages": [],
        "failures": []
    }

    for page_num, rec in enumerate(files, start=1):
        rel_image = rec["path"]
        image_path = root / rel_image

        print(f"[{page_num}/{len(files)}] OCR: {image_path}")

        try:
            img = Image.open(image_path).convert("RGB")
            width, height = img.size

            pdf_page = pdf_doc.new_page(width=width, height=height)
            pdf_page.insert_image(
                fitz.Rect(0, 0, width, height),
                filename=str(image_path)
            )

            blocks = run_ocr(ocr_engine, image_path, args.min_confidence)
            urls = extract_urls(blocks)
            text_lines = [b["text"] for b in blocks]
            plain_text = "\n".join(text_lines)

            insert_text_layer(pdf_page, blocks, visible=args.visible_text)
            add_clickable_links(pdf_page, urls, width=width, height=height, pad=args.link_pad)

            module_dir_rel = rec.get("module_output_directory", rel_image + ".fm.modules")
            module_dir_abs = root / module_dir_rel

            module_filename = f"image_ocr.{run_id}.json"
            module_json_abs = module_dir_abs / module_filename
            module_json_rel = str(Path(module_dir_rel) / module_filename)

            source_sha256 = sha256_file(image_path)

            module_block = {
                "schema": {"name": "FMIAF-module", "version": SCHEMA_VERSION},
                "record_type": "module_output",
                "module": {
                    "name": "image_ocr",
                    "version": TOOL_VERSION,
                    "engine": "PaddleOCR",
                    "language": args.lang,
                    "run_id": run_id,
                    "created_utc": now_utc(),
                    "append_only": True
                },
                "target": {
                    "fm_id": rec["fm_id"],
                    "ff_id": rec["ff_id"],
                    "image_path": rel_image,
                    "source_sha256": source_sha256
                },
                "placement": {
                    "suggested_target": "modules.image_ocr",
                    "merge_strategy": "pointer_append",
                    "overwrite_originals": False
                },
                "data": {
                    "success": True,
                    "pdf": {
                        "path": rel_to_root(output_pdf, root),
                        "page": page_num
                    },
                    "text": {
                        "plain": plain_text,
                        "lines": text_lines
                    },
                    "urls": urls,
                    "blocks": blocks,
                    "bbox_policy": {
                        "ocr_boxes": "textline_or_block_boxes_from_engine",
                        "url_boxes": "anchor_zone_contains_url_not_exact",
                        "clickable_link_padding_px": args.link_pad
                    }
                },
                "provenance": {
                    "tool_name": TOOL_NAME,
                    "tool_version": TOOL_VERSION,
                    "created_utc": now_utc()
                }
            }

            write_json(module_json_abs, module_block)

            index_entry = {
                "schema_version": SCHEMA_VERSION,
                "record_type": "module_index_entry",
                "created_utc": now_utc(),
                "fm_id": rec["fm_id"],
                "ff_id": rec["ff_id"],
                "file": rel_image,
                "module_name": "image_ocr",
                "module_json": module_json_rel,
                "suggested_target": "modules.image_ocr",
                "merge_strategy": "pointer_append",
                "run_id": run_id,
                "append_only": True,
                "source_sha256": source_sha256,
                "tool_name": TOOL_NAME,
                "tool_version": TOOL_VERSION
            }

            append_module_index(module_index, index_entry)

            research["pages"].append({
                "page": page_num,
                "fm_id": rec["fm_id"],
                "ff_id": rec["ff_id"],
                "image": rel_image,
                "source_sha256": source_sha256,
                "width": width,
                "height": height,
                "word_count": len(blocks),
                "url_count": len(urls),
                "text_chars": len(plain_text),
                "module_json": module_json_rel,
                "text": {
                    "plain": plain_text,
                    "lines": text_lines
                },
                "urls": urls,
                "blocks": blocks
            })

            research["summary"]["files_processed"] += 1
            research["summary"]["total_blocks"] += len(blocks)
            research["summary"]["total_urls"] += len(urls)
            research["summary"]["total_text_chars"] += len(plain_text)

            print(f"    module: {module_json_rel}")
            print(f"    blocks: {len(blocks)}")
            print(f"    urls:   {len(urls)}")

        except Exception as e:
            research["summary"]["files_failed"] += 1
            research["failures"].append({
                "page": page_num,
                "file": rel_image,
                "error": str(e)
            })
            print(f"    ERROR: {e}", file=sys.stderr)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf_doc.save(output_pdf, garbage=4, deflate=True)
    pdf_doc.close()

    elapsed = time.time() - started
    research["summary"]["elapsed_seconds"] = elapsed
    research["summary"]["seconds_per_file"] = elapsed / max(1, len(files))

    write_json(output_json, research)

    if args.latest_link and not args.no_timestamp_big_outputs:
        try:
            output_pdf_base.write_bytes(output_pdf.read_bytes())
            write_json(output_json_base, research)
        except Exception as e:
            print(f"WARN: failed to write latest-link outputs: {e}", file=sys.stderr)

    print()
    print(f"Run ID:             {run_id}")
    print(f"PDF saved:          {output_pdf}")
    print(f"Research JSON:      {output_json}")
    print(f"Module index:       {module_index}")
    print(f"Files processed:    {research['summary']['files_processed']}")
    print(f"Files failed:       {research['summary']['files_failed']}")
    print(f"Total blocks:       {research['summary']['total_blocks']}")
    print(f"Total URLs:         {research['summary']['total_urls']}")
    print(f"Elapsed seconds:    {elapsed:.2f}")
    print(f"Seconds per file:   {research['summary']['seconds_per_file']:.4f}")
    print("Append-only OCR module complete.")


if __name__ == "__main__":
    main()
