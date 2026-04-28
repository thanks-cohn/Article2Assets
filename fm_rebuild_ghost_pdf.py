#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

import fitz


SCHEMA_VERSION = "0.1.0"
TOOL_NAME = "fm_rebuild_ghost_pdf"
TOOL_VERSION = "0.1.0"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path):
    rows = []
    with Path(path).expanduser().open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def bbox_xyxy(obj):
    b = obj.get("bbox_xyxy")
    if b and len(b) == 4:
        return [float(v) for v in b]

    wh = obj.get("bbox_xywh")
    if wh and len(wh) == 4:
        x, y, w, h = [float(v) for v in wh]
        return [x, y, x + w, y + h]

    return None


def page_size(row):
    max_x = 1000.0
    max_y = 1000.0

    for obj in row.get("objects", []):
        b = bbox_xyxy(obj)
        if not b:
            continue
        max_x = max(max_x, b[2])
        max_y = max(max_y, b[3])

    return max_x, max_y


def insert_panel(page, obj):
    b = bbox_xyxy(obj)
    if not b:
        return False

    asset = obj.get("asset") or {}
    path = asset.get("path")
    if not path:
        return False

    p = Path(path).expanduser()
    if not p.exists():
        return False

    try:
        page.insert_image(fitz.Rect(*b), filename=str(p))
        return True
    except Exception:
        return False


def insert_text(page, obj, visible=True):
    text = obj.get("text") or ""
    b = bbox_xyxy(obj)
    if not text or not b:
        return False

    x0, y0, x1, y1 = b
    height = max(4.0, y1 - y0)
    fontsize = max(4.0, height * 0.72)

    try:
        page.insert_textbox(
            fitz.Rect(*b),
            text,
            fontsize=fontsize,
            fontname="helv",
            color=(0, 0, 0) if visible else (1, 1, 1),
            render_mode=0,
            align=fitz.TEXT_ALIGN_LEFT,
        )
        return True
    except Exception:
        return False


def draw_debug_boxes(page, obj):
    b = bbox_xyxy(obj)
    if not b:
        return

    kind = obj.get("object_type")
    rect = fitz.Rect(*b)

    if kind == "panel":
        page.draw_rect(rect, color=(1, 0, 0), width=0.75)
    elif kind == "text_line":
        page.draw_rect(rect, color=(0, 0, 1), width=0.25)


def main():
    ap = argparse.ArgumentParser(
        description="Rebuild a ghost PDF from FMIAF canonical JSONL using panel crops and text spatial data."
    )
    ap.add_argument("--canonical-jsonl", required=True)
    ap.add_argument("--output-pdf", required=True)
    ap.add_argument("--debug-boxes", action="store_true")
    ap.add_argument("--no-text", action="store_true")
    ap.add_argument("--no-panels", action="store_true")
    args = ap.parse_args()

    rows = read_jsonl(args.canonical_jsonl)
    doc = fitz.open()

    pages_written = 0
    panels_inserted = 0
    text_inserted = 0

    for row in rows:
        width, height = page_size(row)
        page = doc.new_page(width=width, height=height)

        page.insert_text(
            fitz.Point(20, 24),
            f"Ghost rebuild: {row.get('ids', {}).get('source_file')} page {row.get('page', {}).get('page_number')}",
            fontsize=8,
            color=(0.45, 0.45, 0.45)
        )

        objects = row.get("objects", [])

        if not args.no_panels:
            for obj in objects:
                if obj.get("object_type") == "panel":
                    if insert_panel(page, obj):
                        panels_inserted += 1

        if not args.no_text:
            for obj in objects:
                if obj.get("object_type") == "text_line":
                    if insert_text(page, obj):
                        text_inserted += 1

        if args.debug_boxes:
            for obj in objects:
                draw_debug_boxes(page, obj)

        pages_written += 1

    out = Path(args.output_pdf).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    doc.close()

    print("Ghost PDF rebuild complete.")
    print(f"Created UTC:      {now_utc()}")
    print(f"Pages written:    {pages_written}")
    print(f"Panels inserted:  {panels_inserted}")
    print(f"Text inserted:    {text_inserted}")
    print(f"Output PDF:       {out}")


if __name__ == "__main__":
    main()
