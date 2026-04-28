#!/usr/bin/env python3
"""
FileMonster Comic Panel Detector v0.1

Narrow purpose:
  Detect comic panels as machine-attainable objects.

This module is intentionally separate from fm_layout_regions_module.py.
It creates an append-only FileMonster module layer named: comic_panels

It produces:
  - per-page panel region objects
  - panel crops
  - debug SVGs
  - module JSON per source file
  - filemonster_module_index.jsonl entries

Design goal:
  Text extraction can already happen elsewhere. This module establishes the
  panel/object foundation so spatial text can later be linked to panel zones.
"""

import argparse
import base64
import hashlib
import html
import io
import json
from pathlib import Path
from datetime import datetime, timezone

import cv2
import fitz
import numpy as np
from PIL import Image


SCHEMA_VERSION = "0.1.0"
TOOL_NAME = "fm_comic_panel_detector"
TOOL_VERSION = "0.1.0"


# ----------------------------
# Basic utilities
# ----------------------------


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


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def rel_to_root(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except Exception:
        return str(path)


def media_supported(rec):
    fmt = str(rec.get("format", "")).lower()
    media = str(rec.get("media_type", "")).lower()
    return media in {"image", "document"} and fmt in {"pdf", "png", "jpeg", "jpg", "webp", "bmp", "tiff"}


# ----------------------------
# Page loading
# ----------------------------


def image_to_array(path):
    return np.array(Image.open(path).convert("RGB"))


def render_pdf_page(path, page_index, zoom):
    doc = fitz.open(path)
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    doc.close()
    return arr, float(pix.width), float(pix.height)


def load_pages(path, fmt, pdf_zoom):
    path = Path(path)
    if fmt == "pdf" or path.suffix.lower() == ".pdf":
        doc = fitz.open(path)
        count = len(doc)
        doc.close()
        return [(i + 1, *render_pdf_page(path, i, pdf_zoom)) for i in range(count)]

    arr = image_to_array(path)
    h, w = arr.shape[:2]
    return [(1, arr, float(w), float(h))]


# ----------------------------
# Geometry
# ----------------------------


def bbox_area(b):
    if not b or len(b) != 4:
        return 0.0
    return max(0.0, float(b[2]) - float(b[0])) * max(0.0, float(b[3]) - float(b[1]))


def bbox_iou(a, b):
    ax0, ay0, ax1, ay1 = map(float, a)
    bx0, by0, bx1, by1 = map(float, b)
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = bbox_area(a) + bbox_area(b) - inter
    return 0.0 if union <= 0 else inter / union


def bbox_overlap_ratio(smaller, larger):
    sx0, sy0, sx1, sy1 = map(float, smaller)
    lx0, ly0, lx1, ly1 = map(float, larger)
    ix0 = max(sx0, lx0)
    iy0 = max(sy0, ly0)
    ix1 = min(sx1, lx1)
    iy1 = min(sy1, ly1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    denom = bbox_area(smaller)
    return 0.0 if denom <= 0 else inter / denom


def polygon_from_bbox(b):
    x0, y0, x1, y1 = map(float, b)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def crop_region(arr, bbox):
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(w, int(round(x0))))
    y0 = max(0, min(h, int(round(y0))))
    x1 = max(0, min(w, int(round(x1))))
    y1 = max(0, min(h, int(round(y1))))
    if x1 <= x0 or y1 <= y0:
        return None
    return arr[y0:y1, x0:x1]


def save_crop_png(crop, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(crop).save(path)
    data = path.read_bytes()
    return {
        "path": path.name,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
    }


# ----------------------------
# Detection passes
# ----------------------------


def normalize_page(arr):
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    # Gentle denoise. Comics contain ink texture, so keep this small.
    gray = cv2.medianBlur(gray, 3)
    return gray


def rectangle_from_contour(c, page_area, min_area_ratio, max_area_ratio, min_side, rectangularity_min, source):
    area = float(cv2.contourArea(c))
    if area <= 0:
        return None

    x, y, w, h = cv2.boundingRect(c)
    if w < min_side or h < min_side:
        return None

    bbox = [float(x), float(y), float(x + w), float(y + h)]
    box_area = max(1.0, float(w * h))
    area_ratio = box_area / max(1.0, page_area)
    if area_ratio < min_area_ratio or area_ratio > max_area_ratio:
        return None

    rectangularity = min(1.0, area / box_area)
    if rectangularity < rectangularity_min:
        return None

    aspect = w / max(1.0, h)
    if aspect < 0.08 or aspect > 12.0:
        return None

    return {
        "bbox": bbox,
        "polygon": polygon_from_bbox(bbox),
        "area": box_area,
        "area_ratio": area_ratio,
        "rectangularity": float(rectangularity),
        "confidence": float(min(1.0, 0.50 + rectangularity * 0.45)),
        "evidence": [source, "rectangle_like_contour"],
    }


def detect_border_boxes(arr, args):
    """Find ink/border closed rectangles and square-ish boxes."""
    gray = normalize_page(arr)
    h, w = gray.shape[:2]
    page_area = float(w * h)

    regions = []
    passes = [
        ("border_canny_strong", 40, 130, 1, 0.28),
        ("border_canny_medium", 24, 95, 2, 0.22),
        ("border_canny_faint", 12, 55, 2, 0.18),
    ]

    for name, c1, c2, dilate_iter, rect_min in passes:
        edges = cv2.Canny(gray, c1, c2)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=dilate_iter)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            r = rectangle_from_contour(
                c,
                page_area=page_area,
                min_area_ratio=args.min_area_ratio,
                max_area_ratio=args.max_area_ratio,
                min_side=args.min_side,
                rectangularity_min=rect_min,
                source=name,
            )
            if r:
                regions.append(r)

    return regions


def detect_white_panel_interiors(arr, args):
    """Find pale rectangular interiors/gutters that imply boxed panel zones."""
    gray = normalize_page(arr)
    h, w = gray.shape[:2]
    page_area = float(w * h)

    # Threshold very light zones. This catches white gutters and blank panel interiors.
    _, mask = cv2.threshold(gray, args.white_threshold, 255, cv2.THRESH_BINARY)

    # Close speech balloon holes and small ink scratches inside otherwise pale zones.
    close_k = max(3, int(args.gutter_close_kernel))
    if close_k % 2 == 0:
        close_k += 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close_k, close_k), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []

    for c in contours:
        r = rectangle_from_contour(
            c,
            page_area=page_area,
            min_area_ratio=args.min_area_ratio,
            max_area_ratio=args.max_area_ratio,
            min_side=args.min_side,
            rectangularity_min=0.30,
            source="white_rectangular_zone",
        )
        if r:
            # These are weaker evidence than actual borders.
            r["confidence"] = min(r["confidence"], 0.62)
            r["evidence"].append("pale_zone_candidate")
            regions.append(r)

    return regions


def detect_art_masses(arr, args):
    """Find large non-white connected artwork masses for borderless or faint-border panels."""
    gray = normalize_page(arr)
    h, w = gray.shape[:2]
    page_area = float(w * h)

    # Anything darker than near-white is content. Close into masses.
    mask = cv2.threshold(gray, args.art_threshold, 255, cv2.THRESH_BINARY_INV)[1]
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []

    for c in contours:
        r = rectangle_from_contour(
            c,
            page_area=page_area,
            min_area_ratio=args.min_area_ratio,
            max_area_ratio=args.max_area_ratio,
            min_side=args.min_side,
            rectangularity_min=0.12,
            source="art_mass",
        )
        if r:
            r["confidence"] = min(r["confidence"], 0.55)
            r["evidence"].append("borderless_or_faint_panel_fallback")
            regions.append(r)

    return regions


def remove_page_frame(regions, width, height, cutoff_ratio):
    page_bbox = [0.0, 0.0, float(width), float(height)]
    out = []
    for r in regions:
        if r["area_ratio"] > cutoff_ratio and bbox_iou(r["bbox"], page_bbox) > 0.72:
            continue
        out.append(r)
    return out


def merge_regions(regions, merge_iou):
    """Merge duplicate panel detections while preserving evidence."""
    kept = []

    for r in sorted(regions, key=lambda x: (x.get("confidence", 0), x.get("area", 0)), reverse=True):
        matched = None
        for k in kept:
            if bbox_iou(r["bbox"], k["bbox"]) >= merge_iou:
                matched = k
                break
            # Inner duplicate: one method found the same panel slightly smaller.
            if bbox_overlap_ratio(r["bbox"], k["bbox"]) > 0.88 or bbox_overlap_ratio(k["bbox"], r["bbox"]) > 0.88:
                matched = k
                break

        if matched is None:
            kept.append(dict(r))
            continue

        matched["confidence"] = max(float(matched.get("confidence", 0)), float(r.get("confidence", 0)))
        evidence = list(dict.fromkeys((matched.get("evidence") or []) + (r.get("evidence") or [])))
        matched["evidence"] = evidence

        # Prefer the larger bbox if confidence is similar, because it is safer for panel crops.
        if bbox_area(r["bbox"]) > bbox_area(matched["bbox"]) and r.get("confidence", 0) >= matched.get("confidence", 0) - 0.08:
            matched["bbox"] = r["bbox"]
            matched["polygon"] = polygon_from_bbox(r["bbox"])
            matched["area"] = bbox_area(r["bbox"])
            matched["area_ratio"] = r.get("area_ratio", matched.get("area_ratio"))
            matched["rectangularity"] = max(matched.get("rectangularity", 0), r.get("rectangularity", 0))

    return kept


def suppress_containers(regions, container_overlap):
    """Remove large boxes that only contain smaller panel boxes, except when alone."""
    out = []
    for i, r in enumerate(regions):
        contained = []
        for j, other in enumerate(regions):
            if i == j:
                continue
            if bbox_area(other["bbox"]) >= bbox_area(r["bbox"]):
                continue
            if bbox_overlap_ratio(other["bbox"], r["bbox"]) >= container_overlap:
                contained.append(other)

        # If a big region contains multiple smaller regions, it is probably a page/group box.
        if len(contained) >= 2 and bbox_area(r["bbox"]) > sum(bbox_area(x["bbox"]) for x in contained) * 0.75:
            continue
        out.append(r)
    return out


def assign_order_and_ids(regions, page_no):
    # Simple western reading order: top-to-bottom, left-to-right.
    # Future branch can add manga/right-to-left mode.
    sorted_regions = sorted(regions, key=lambda r: (round(r["bbox"][1] / 40.0), r["bbox"][0], r["bbox"][1]))
    for i, r in enumerate(sorted_regions, start=1):
        r["region_id"] = f"P{page_no}_CP{i}"
        r["page"] = page_no
        r["reading_order"] = i
        r["region_type"] = "comic_panel"
        r["block_type"] = "comic_panel_region"
        r["asset_type"] = "comic_panel_crop"
    return sorted_regions


def detect_comic_panels(arr, page_no, args):
    h, w = arr.shape[:2]
    regions = []

    if not args.no_border_pass:
        regions.extend(detect_border_boxes(arr, args))
    if not args.no_white_pass:
        regions.extend(detect_white_panel_interiors(arr, args))
    if not args.no_art_pass:
        regions.extend(detect_art_masses(arr, args))

    regions = remove_page_frame(regions, w, h, args.page_frame_cutoff)
    regions = merge_regions(regions, args.merge_iou)
    regions = suppress_containers(regions, args.container_overlap)
    regions = [r for r in regions if bbox_area(r["bbox"]) >= args.min_area_ratio * float(w * h)]
    regions = assign_order_and_ids(regions, page_no)
    return regions


# ----------------------------
# Output helpers
# ----------------------------


def region_to_block(r):
    return {
        "block_id": r["region_id"],
        "block_type": r.get("block_type", "comic_panel_region"),
        "region_type": r.get("region_type", "comic_panel"),
        "asset_type": r.get("asset_type", "comic_panel_crop"),
        "page": r.get("page"),
        "bbox": r.get("bbox"),
        "polygon": r.get("polygon"),
        "reading_order": r.get("reading_order"),
        "confidence": r.get("confidence"),
        "area": r.get("area"),
        "area_ratio": r.get("area_ratio"),
        "rectangularity": r.get("rectangularity"),
        "crop": r.get("crop"),
        "evidence": r.get("evidence", []),
        "label": "comic_panel",
    }


def arr_to_png_base64(arr):
    bio = io.BytesIO()
    Image.fromarray(arr).save(bio, format="PNG")
    return base64.b64encode(bio.getvalue()).decode("ascii")


def debug_svg(width, height, arr, regions, embed_background=True):
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    )
    if embed_background:
        b64 = arr_to_png_base64(arr)
        parts.append(f'<image id="page_background" href="data:image/png;base64,{b64}" x="0" y="0" width="{width}" height="{height}"/>')
    else:
        parts.append('<rect id="page_background" x="0" y="0" width="100%" height="100%" fill="white"/>')

    parts.append('<g id="comic_panel_regions" class="comic-panel-regions">')
    for r in regions:
        rid = html.escape(r.get("region_id", ""))
        x0, y0, x1, y1 = r["bbox"]
        pts = " ".join(f"{x},{y}" for x, y in r["polygon"])
        title = html.escape(json.dumps({
            "region_id": r.get("region_id"),
            "bbox": r.get("bbox"),
            "reading_order": r.get("reading_order"),
            "confidence": r.get("confidence"),
            "evidence": r.get("evidence"),
            "crop": r.get("crop"),
        }, ensure_ascii=False))
        parts.append(f'<g id="{rid}" class="comic-panel" data-region-id="{rid}">')
        parts.append(f'<title>{title}</title>')
        parts.append(f'<polygon points="{pts}" fill="none" stroke="red" stroke-width="4" opacity="0.95"/>')
        parts.append(f'<text x="{x0}" y="{max(16, y0 - 6)}" font-family="Arial, sans-serif" font-size="16" fill="red">{rid}</text>')
        parts.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="yellow" stroke-width="1" opacity="0.7"/>')
        parts.append('</g>')
    parts.append('</g>')
    parts.append('</svg>')
    return "\n".join(parts)


def process_file(rec, root, module_index_path, run_id, args):
    rel = rec.get("path")
    fmt = rec.get("format", "")
    src_path = root / rel
    if not src_path.exists():
        print(f"SKIP missing source: {rel}")
        return None

    module_dir_rel = rec.get("module_output_directory", rel + ".fm.modules")
    module_dir = root / module_dir_rel
    module_dir.mkdir(parents=True, exist_ok=True)

    source_sha = sha256_file(src_path)
    pages = load_pages(src_path, fmt, args.pdf_zoom)

    pages_out = []
    all_regions = []
    all_blocks = []
    debug_svgs = []

    for page_no, arr, width, height in pages:
        regions = detect_comic_panels(arr, page_no, args)

        for r in regions:
            crop = crop_region(arr, r["bbox"])
            if crop is not None:
                crop_name = f"comic_panels.{run_id}.p{page_no:04d}.{r['region_id']}.png"
                r["crop"] = save_crop_png(crop, module_dir / crop_name)
            else:
                r["crop"] = None

        svg_name = f"comic_panels.{run_id}.p{page_no:04d}.debug.svg"
        svg_path = module_dir / svg_name
        svg_path.write_text(debug_svg(width, height, arr, regions, embed_background=not args.no_embed_debug_background), encoding="utf-8")
        debug_svgs.append(svg_name)

        blocks = [region_to_block(r) for r in regions]
        all_regions.extend(regions)
        all_blocks.extend(blocks)

        pages_out.append({
            "page": page_no,
            "width": width,
            "height": height,
            "region_count": len(regions),
            "regions": regions,
            "debug_svg": svg_name,
        })

    module_json_name = f"comic_panels.{run_id}.json"
    module_json_rel = f"{module_dir_rel}/{module_json_name}"
    module_json_abs = module_dir / module_json_name

    module = {
        "schema": {"name": "FMIAF-module", "version": SCHEMA_VERSION},
        "record_type": "filemonster_module_output",
        "module": {
            "name": "comic_panels",
            "version": TOOL_VERSION,
            "tool": TOOL_NAME,
            "created_utc": now_utc(),
            "run_id": run_id,
        },
        "target": {
            "fm_id": rec.get("fm_id"),
            "ff_id": rec.get("ff_id"),
            "path": rel,
            "media_type": rec.get("media_type"),
            "format": rec.get("format"),
            "source_sha256": source_sha,
        },
        "placement": {
            "module_dir": module_dir_rel,
            "module_json": module_json_rel,
            "debug_svgs": debug_svgs,
        },
        "parameters": {
            "pdf_zoom": args.pdf_zoom,
            "min_area_ratio": args.min_area_ratio,
            "max_area_ratio": args.max_area_ratio,
            "min_side": args.min_side,
            "merge_iou": args.merge_iou,
            "white_threshold": args.white_threshold,
            "art_threshold": args.art_threshold,
            "page_frame_cutoff": args.page_frame_cutoff,
            "container_overlap": args.container_overlap,
            "passes": {
                "border": not args.no_border_pass,
                "white": not args.no_white_pass,
                "art": not args.no_art_pass,
            },
        },
        "data": {
            "text": {"plain": "", "sources": []},
            "urls": [],
            "blocks": all_blocks,
            "regions": all_regions,
            "relationships": [],
            "pages": pages_out,
            "summary": {
                "page_count": len(pages_out),
                "region_count": len(all_regions),
                "crop_count": len([r for r in all_regions if r.get("crop")]),
            },
        },
    }

    write_json(module_json_abs, module)

    index_entry = {
        "created_utc": now_utc(),
        "run_id": run_id,
        "fm_id": rec.get("fm_id"),
        "ff_id": rec.get("ff_id"),
        "file": rel,
        "module_name": "comic_panels",
        "module_version": TOOL_VERSION,
        "module_json": module_json_rel,
        "module_dir": module_dir_rel,
        "source_sha256": source_sha,
        "summary": module["data"]["summary"],
    }
    append_jsonl(module_index_path, index_entry)

    print(f"[comic_panels] {rel}")
    print(f"  module: {module_json_rel}")
    print(f"  pages:  {len(pages_out)}")
    print(f"  panels: {len(all_regions)}")
    print(f"  svgs:   {len(debug_svgs)}")

    return module


# ----------------------------
# CLI
# ----------------------------


def main():
    parser = argparse.ArgumentParser(
        description="FileMonster comic panel detector: detect boxed comic panels, crop them, and emit module JSON."
    )
    parser.add_argument("--master", required=True, help="FileMonster master JSON")
    parser.add_argument("--module-index", default=None, help="Defaults beside master as filemonster_module_index.jsonl")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--pdf-zoom", type=float, default=2.0)

    parser.add_argument("--min-area-ratio", type=float, default=0.0025, help="Minimum panel area as fraction of page")
    parser.add_argument("--max-area-ratio", type=float, default=0.88, help="Maximum panel area as fraction of page")
    parser.add_argument("--min-side", type=int, default=42, help="Minimum width/height in rendered pixels")
    parser.add_argument("--merge-iou", type=float, default=0.70)
    parser.add_argument("--container-overlap", type=float, default=0.90)
    parser.add_argument("--page-frame-cutoff", type=float, default=0.90)

    parser.add_argument("--white-threshold", type=int, default=238, help="Threshold for pale gutter/interior pass")
    parser.add_argument("--gutter-close-kernel", type=int, default=13)
    parser.add_argument("--art-threshold", type=int, default=245, help="Threshold for non-white art mass pass")

    parser.add_argument("--no-border-pass", action="store_true")
    parser.add_argument("--no-white-pass", action="store_true")
    parser.add_argument("--no-art-pass", action="store_true")
    parser.add_argument("--no-embed-debug-background", action="store_true", help="Make debug SVG smaller by omitting page background")

    args = parser.parse_args()

    run_id = args.run_id or make_run_id()
    master_path = Path(args.master).expanduser().resolve()
    master = read_json(master_path)
    root = Path(master["root_path_at_scan"]).expanduser().resolve()

    module_index_path = (
        Path(args.module_index).expanduser().resolve()
        if args.module_index
        else master_path.parent / "filemonster_module_index.jsonl"
    )

    files = [rec for rec in master.get("files", []) if media_supported(rec)]
    processed = 0
    skipped = 0
    failed = 0

    for rec in files:
        try:
            mod = process_file(rec, root, module_index_path, run_id, args)
            if mod is None:
                skipped += 1
            else:
                processed += 1
        except Exception as e:
            failed += 1
            print(f"ERROR processing {rec.get('path')}: {e}")

    print("\nComic panel detection complete.")
    print(f"Run ID:      {run_id}")
    print(f"Files found: {len(files)}")
    print(f"Processed:   {processed}")
    print(f"Skipped:     {skipped}")
    print(f"Failed:      {failed}")
    print(f"Module index:{module_index_path}")


if __name__ == "__main__":
    main()
