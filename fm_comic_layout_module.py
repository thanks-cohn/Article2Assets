#!/usr/bin/env python3
"""
FileMonster Comic Layout Module v0.1

Goal:
  Text first. Panels second. Relationships third.

This module creates a comic-aware layer that:
  - renders PDF/image pages
  - captures text objects as independent line objects
  - detects forgiving panel candidates
  - crops panels
  - assigns text to panels with forgiving margins
  - writes module JSON and debug SVG
  - appends to filemonster_module_index.jsonl

It does NOT replace fm_layout_regions_module.py.
It creates a separate module layer named: comic_layout
"""

import argparse
import base64
import hashlib
import html
import io
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import cv2
import fitz
import numpy as np
from PIL import Image

try:
    import pytesseract
except Exception:
    pytesseract = None


SCHEMA_VERSION = "0.1.0"
TOOL_NAME = "fm_comic_layout_module"
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


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


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


def newest_module(entries, module_name, fm_id):
    matches = [
        e for e in entries
        if e.get("module_name") == module_name and e.get("fm_id") == fm_id
    ]
    return sorted(matches, key=lambda e: e.get("run_id", ""))[-1] if matches else None


# ----------------------------
# Geometry
# ----------------------------


def bbox_area(b):
    if not b or len(b) != 4:
        return 0.0
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def bbox_center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def inflate_bbox(b, margin, width, height):
    return [
        max(0.0, b[0] - margin),
        max(0.0, b[1] - margin),
        min(float(width), b[2] + margin),
        min(float(height), b[3] + margin),
    ]


def contains_point(b, x, y):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def bbox_overlap(a, b):
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def iou_bbox(a, b):
    inter = bbox_overlap(a, b)
    union = bbox_area(a) + bbox_area(b) - inter
    return 0.0 if union <= 0 else inter / union


def dist_bbox_centers(a, b):
    ax, ay = bbox_center(a)
    bx, by = bbox_center(b)
    return math.hypot(ax - bx, ay - by)


def bbox_from_contour(c):
    x, y, w, h = cv2.boundingRect(c)
    return [float(x), float(y), float(x + w), float(y + h)]


def polygon_from_bbox(b):
    return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]


# ----------------------------
# Page loading / rendering
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


def load_pages(path, fmt, zoom):
    path = Path(path)
    if fmt == "pdf" or path.suffix.lower() == ".pdf":
        doc = fitz.open(path)
        count = len(doc)
        doc.close()
        return [(i + 1, *render_pdf_page(path, i, zoom)) for i in range(count)]

    arr = image_to_array(path)
    h, w = arr.shape[:2]
    return [(1, arr, float(w), float(h))]


# ----------------------------
# Text first
# ----------------------------


def scale_text_line(line, scale):
    b = line.get("bbox") or [0, 0, 0, 0]
    return {
        "text_id": line.get("id") or line.get("block_id"),
        "page": line.get("page"),
        "text": line.get("text", ""),
        "bbox": [float(v) * scale for v in b],
        "source": "spatial_text",
        "confidence": line.get("confidence"),
        "raw": line,
    }


def extract_spatial_text_for_page(spatial_pages, page_no, scale):
    page = spatial_pages.get(page_no) or {}
    lines = page.get("lines") or page.get("objects") or []
    out = []
    for i, line in enumerate(lines, start=1):
        text = str(line.get("text", "")).strip()
        if not text:
            continue
        obj = scale_text_line(line, scale)
        if not obj.get("text_id"):
            obj["text_id"] = f"P{page_no}_T{i}"
        out.append(obj)
    return out


def tesseract_lines(arr, page_no, min_conf=20):
    if pytesseract is None:
        return []

    img = Image.fromarray(arr)
    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    grouped = {}
    n = len(data.get("text", []))
    for i in range(n):
        txt = str(data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data.get("conf", [0])[i])
        except Exception:
            conf = 0.0
        if conf < min_conf:
            continue

        key = (
            data.get("block_num", [0])[i],
            data.get("par_num", [0])[i],
            data.get("line_num", [0])[i],
        )
        x = float(data["left"][i])
        y = float(data["top"][i])
        w = float(data["width"][i])
        h = float(data["height"][i])

        g = grouped.setdefault(key, {"words": [], "boxes": [], "confs": []})
        g["words"].append(txt)
        g["boxes"].append([x, y, x + w, y + h])
        g["confs"].append(conf)

    lines = []
    for idx, (_, g) in enumerate(sorted(grouped.items()), start=1):
        boxes = g["boxes"]
        bbox = [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ]
        lines.append({
            "text_id": f"P{page_no}_OCRL{idx}",
            "page": page_no,
            "text": " ".join(g["words"]),
            "bbox": bbox,
            "source": "tesseract_fallback",
            "confidence": sum(g["confs"]) / max(1, len(g["confs"])),
            "raw": None,
        })
    return lines


def get_text_objects(arr, page_no, spatial_pages, scale, use_ocr_fallback, min_ocr_conf):
    text = extract_spatial_text_for_page(spatial_pages, page_no, scale)
    if text:
        return text
    if use_ocr_fallback:
        return tesseract_lines(arr, page_no, min_conf=min_ocr_conf)
    return []


# ----------------------------
# Comic panel detection
# ----------------------------


def preprocess_for_panels(arr):
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    # Comics often have texture. Median blur removes tiny noise while preserving borders.
    blur = cv2.medianBlur(gray, 3)

    # Ink/dark-line emphasis.
    edges = cv2.Canny(blur, 35, 120)

    # Close broken panel borders.
    kernel_close = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_close, iterations=2)

    # Slight dilation helps faint gutters/borders become connected contours.
    kernel_dilate = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(closed, kernel_dilate, iterations=1)

    return dilated


def detect_panel_candidates(arr, min_area_ratio=0.004, max_area_ratio=0.92, merge_iou=0.72):
    h, w = arr.shape[:2]
    page_area = float(w * h)
    mask = preprocess_for_panels(arr)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw = []
    for c in contours:
        area = float(cv2.contourArea(c))
        if area <= 0:
            continue
        ratio = area / page_area
        if ratio < min_area_ratio or ratio > max_area_ratio:
            continue

        bbox = bbox_from_contour(c)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        if bw < 40 or bh < 40:
            continue

        rect_area = max(1.0, bw * bh)
        rectangularity = min(1.0, area / rect_area)

        # We accept messy comics, so do not require high rectangularity.
        if rectangularity < 0.22:
            continue

        raw.append({
            "bbox": bbox,
            "polygon": polygon_from_bbox(bbox),
            "area": bbox_area(bbox),
            "area_ratio": bbox_area(bbox) / page_area,
            "rectangularity": rectangularity,
            "confidence": float(min(1.0, 0.45 + rectangularity * 0.55)),
            "region_type": "comic_panel_candidate",
            "panel_type": "bordered_or_art_mass_candidate",
            "evidence": ["edge_contour", "comic_preprocess"],
        })

    # Remove near-full-page panels unless it is the only thing found.
    filtered = []
    for r in raw:
        if r["area_ratio"] > 0.88 and len(raw) > 1:
            continue
        filtered.append(r)

    # Merge duplicates.
    kept = []
    for r in sorted(filtered, key=lambda x: x["area"], reverse=True):
        if any(iou_bbox(r["bbox"], k["bbox"]) > merge_iou for k in kept):
            continue
        kept.append(r)

    return sorted(kept, key=lambda r: (r["bbox"][1], r["bbox"][0]))


def add_text_anchor_regions(panel_candidates, text_objects, width, height, text_margin):
    """If panel detection misses, text anchors still create useful loose regions."""
    anchors = []
    for t in text_objects:
        b = t["bbox"]
        if bbox_area(b) <= 0:
            continue
        inflated = inflate_bbox(b, text_margin * 1.8, width, height)
        anchors.append({
            "bbox": inflated,
            "polygon": polygon_from_bbox(inflated),
            "area": bbox_area(inflated),
            "area_ratio": bbox_area(inflated) / max(1.0, width * height),
            "rectangularity": 1.0,
            "confidence": 0.35,
            "region_type": "text_anchor_region",
            "panel_type": "text_anchor_fallback",
            "evidence": ["text_anchor", "forgiving_fallback"],
        })

    candidates = panel_candidates[:]
    for a in anchors:
        # Only add if it is not already inside a candidate.
        if any(bbox_overlap(a["bbox"], p["bbox"]) / max(1.0, bbox_area(a["bbox"])) > 0.60 for p in candidates):
            continue
        candidates.append(a)

    return sorted(candidates, key=lambda r: (r["bbox"][1], r["bbox"][0]))


def assign_ids_and_order(regions, page_no):
    for i, r in enumerate(regions, start=1):
        r["region_id"] = f"P{page_no}_CP{i}"
        r["page"] = page_no
        r["reading_order"] = i
    return regions


# ----------------------------
# Crops / SVG / relationships
# ----------------------------


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


def save_crop(crop, path):
    Image.fromarray(crop).save(path)
    data = path.read_bytes()
    return {
        "path": path.name,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def add_crops(arr, regions, module_dir, run_id):
    for r in regions:
        crop = crop_region(arr, r["bbox"])
        if crop is None:
            r["crop"] = None
            continue
        name = f"comic_layout.{run_id}.{r['region_id']}.png"
        r["crop"] = save_crop(crop, module_dir / name)
    return regions


def assign_text_to_panels(text_objects, regions, width, height, text_margin, nearest_distance):
    panel_text = {r["region_id"]: [] for r in regions}
    relationships = []

    for t in text_objects:
        tb = t["bbox"]
        tcx, tcy = bbox_center(tb)

        candidates = []
        for r in regions:
            rb = r["bbox"]
            inflated = inflate_bbox(rb, text_margin, width, height)
            overlap = bbox_overlap(tb, inflated)

            if overlap > 0 or contains_point(inflated, tcx, tcy):
                candidates.append((r, 0.0, overlap, "inflated_bbox_overlap_or_center"))
            else:
                d = dist_bbox_centers(tb, rb)
                if d <= nearest_distance:
                    candidates.append((r, d, 0.0, "nearest_panel_within_distance"))

        if candidates:
            # Prefer overlap, then nearest, then smaller panel.
            candidates.sort(key=lambda x: (-x[2], x[1], bbox_area(x[0]["bbox"])))
            best, distance, overlap, policy = candidates[0]
            panel_text[best["region_id"]].append(t)
            relationships.append({
                "relationship_type": "text_assigned_to_comic_panel",
                "from_object_id": t["text_id"],
                "to_object_id": best["region_id"],
                "text": t["text"],
                "bbox": tb,
                "assignment_policy": policy,
                "distance_px": distance,
                "overlap_area": overlap,
                "candidate_panel_ids": [c[0]["region_id"] for c in candidates[:5]],
            })
        else:
            relationships.append({
                "relationship_type": "unassigned_comic_text",
                "from_object_id": t["text_id"],
                "to_object_id": None,
                "text": t["text"],
                "bbox": tb,
                "assignment_policy": "no_panel_within_margin_or_distance",
            })

    return panel_text, relationships


def arr_to_b64_png(arr):
    bio = io.BytesIO()
    Image.fromarray(arr).save(bio, format="PNG")
    return base64.b64encode(bio.getvalue()).decode("ascii")


def make_debug_svg(arr, regions, text_objects, relationships, width, height):
    bg = arr_to_b64_png(arr)
    assigned = {r.get("from_object_id"): r for r in relationships if r.get("to_object_id")}

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    parts.append(f'<image id="page_background" href="data:image/png;base64,{bg}" x="0" y="0" width="{width}" height="{height}"/>')

    parts.append('<g id="comic_panel_candidates">')
    for r in regions:
        x0, y0, x1, y1 = r["bbox"]
        rid = html.escape(r["region_id"])
        title = html.escape(json.dumps({k: r.get(k) for k in ["region_id", "region_type", "panel_type", "confidence", "evidence", "bbox"]}, ensure_ascii=False))
        parts.append(f'<g id="{rid}" class="comic-panel-candidate">')
        parts.append(f'<title>{title}</title>')
        parts.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="none" stroke="red" stroke-width="3" opacity="0.9"/>')
        parts.append(f'<text x="{x0}" y="{max(14, y0-6)}" font-size="16" fill="red">{rid}</text>')
        parts.append('</g>')
    parts.append('</g>')

    parts.append('<g id="comic_text_line_objects">')
    for t in text_objects:
        x0, y0, x1, y1 = t["bbox"]
        tid = html.escape(t["text_id"])
        txt = html.escape(t["text"])
        color = "blue" if tid in assigned else "purple"
        fs = max(5, (y1 - y0) * 0.75)
        meta = html.escape(json.dumps(t, ensure_ascii=False))
        parts.append(f'<g id="{tid}" class="comic-text-line-object">')
        parts.append(f'<title>{meta}</title>')
        parts.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="none" stroke="{color}" stroke-width="1" opacity="0.6"/>')
        parts.append(f'<text x="{x0}" y="{y1}" font-family="Arial, sans-serif" font-size="{fs}" fill="{color}">{txt}</text>')
        parts.append('</g>')
    parts.append('</g>')

    parts.append('</svg>')
    return "\n".join(parts)


# ----------------------------
# Main processing
# ----------------------------


def process_file(rec, root, module_index, entries, run_id, args):
    rel = rec["path"]
    fmt = rec.get("format", "")
    src_path = root / rel
    source_sha = sha256_file(src_path)

    module_dir_rel = rec.get("module_output_directory", rel + ".fm.modules")
    module_dir = root / module_dir_rel
    module_dir.mkdir(parents=True, exist_ok=True)

    spatial_pages = {}
    spatial_entry = newest_module(entries, "spatial_text", rec.get("fm_id"))
    spatial_module_rel = None
    if spatial_entry:
        spatial_module_rel = spatial_entry.get("module_json")
        try:
            spatial = read_json(root / spatial_module_rel)
            spatial_pages = {
                p.get("page"): p
                for p in spatial.get("data", {}).get("pages", [])
                if p.get("page") is not None
            }
        except Exception:
            spatial_pages = {}

    pages = load_pages(src_path, fmt, args.pdf_zoom)

    pages_out = []
    all_regions = []
    all_text_objects = []
    all_relationships = []
    svg_files = []
    crop_files = []

    for page_no, arr, width, height in pages:
        text_objects = get_text_objects(
            arr=arr,
            page_no=page_no,
            spatial_pages=spatial_pages,
            scale=args.pdf_zoom,
            use_ocr_fallback=args.ocr_fallback,
            min_ocr_conf=args.min_ocr_confidence,
        )

        regions = detect_panel_candidates(
            arr,
            min_area_ratio=args.min_area_ratio,
            max_area_ratio=args.max_area_ratio,
            merge_iou=args.merge_iou,
        )

        if args.text_anchor_regions:
            regions = add_text_anchor_regions(
                regions,
                text_objects,
                width,
                height,
                args.text_margin,
            )

        regions = assign_ids_and_order(regions, page_no)
        regions = add_crops(arr, regions, module_dir, run_id)
        crop_files.extend([r["crop"] for r in regions if r.get("crop")])

        panel_text, relationships = assign_text_to_panels(
            text_objects,
            regions,
            width,
            height,
            text_margin=args.text_margin,
            nearest_distance=args.nearest_text_distance,
        )

        for r in regions:
            r["text_inside"] = panel_text.get(r["region_id"], [])
            r["text_inside_count"] = len(r["text_inside"])

        if args.svg:
            svg_name = f"comic_layout.{run_id}.p{page_no:04d}.svg"
            (module_dir / svg_name).write_text(
                make_debug_svg(arr, regions, text_objects, relationships, width, height),
                encoding="utf-8",
            )
            svg_files.append(svg_name)

        pages_out.append({
            "page": page_no,
            "width": width,
            "height": height,
            "text_object_count": len(text_objects),
            "panel_candidate_count": len(regions),
            "relationship_count": len(relationships),
            "svg": svg_name if args.svg else None,
            "text_objects": text_objects,
            "regions": regions,
            "relationships": relationships,
        })

        all_regions.extend(regions)
        all_text_objects.extend(text_objects)
        all_relationships.extend(relationships)

    module_name = f"comic_layout.{run_id}.json"
    module_path = module_dir / module_name
    module_rel = str(Path(module_dir_rel) / module_name)

    module_json = {
        "schema": {"name": "FMIAF-module", "version": SCHEMA_VERSION},
        "record_type": "module_output",
        "module": {
            "name": "comic_layout",
            "version": TOOL_VERSION,
            "engine": "text_first_forgiving_comic_panel_detector",
            "run_id": run_id,
            "created_utc": now_utc(),
            "append_only": True,
        },
        "target": {
            "fm_id": rec.get("fm_id"),
            "ff_id": rec.get("ff_id"),
            "file_path": rel,
            "source_sha256": source_sha,
        },
        "placement": {
            "suggested_target": "modules.comic_layout",
            "merge_strategy": "pointer_append",
            "overwrite_originals": False,
        },
        "data": {
            "success": True,
            "source": "rendered_page_plus_text_objects",
            "region_family": "comic_panel_candidates",
            "asset_family": "comic_panel_crop",
            "svg_pages": svg_files,
            "crop_files": crop_files,
            "parameters": {
                "pdf_zoom": args.pdf_zoom,
                "min_area_ratio": args.min_area_ratio,
                "max_area_ratio": args.max_area_ratio,
                "merge_iou": args.merge_iou,
                "text_margin": args.text_margin,
                "nearest_text_distance": args.nearest_text_distance,
                "ocr_fallback": args.ocr_fallback,
                "min_ocr_confidence": args.min_ocr_confidence,
                "text_anchor_regions": args.text_anchor_regions,
            },
            "text": {
                "plain": "\n".join(t.get("text", "") for t in all_text_objects if t.get("text")),
                "objects": all_text_objects,
            },
            "regions": all_regions,
            "blocks": all_regions,
            "relationships": all_relationships,
            "pages": pages_out,
        },
        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "created_utc": now_utc(),
            "source_spatial_text_module": spatial_module_rel,
        },
    }

    write_json(module_path, module_json)

    append_jsonl(module_index, {
        "schema_version": SCHEMA_VERSION,
        "record_type": "module_index_entry",
        "created_utc": now_utc(),
        "fm_id": rec.get("fm_id"),
        "ff_id": rec.get("ff_id"),
        "file": rel,
        "module_name": "comic_layout",
        "module_json": module_rel,
        "suggested_target": "modules.comic_layout",
        "merge_strategy": "pointer_append",
        "run_id": run_id,
        "append_only": True,
        "source_sha256": source_sha,
        "tool_name": TOOL_NAME,
        "tool_version": TOOL_VERSION,
    })

    return {
        "module_rel": module_rel,
        "pages": len(pages_out),
        "text_objects": len(all_text_objects),
        "regions": len(all_regions),
        "relationships": len(all_relationships),
        "crops": len(crop_files),
        "svgs": len(svg_files),
    }


def main():
    parser = argparse.ArgumentParser(
        description="FileMonster comic layout module: text-first forgiving comic panel candidates."
    )

    parser.add_argument("--master", required=True)
    parser.add_argument("--module-index", default=None)
    parser.add_argument("--run-id", default=None)

    parser.add_argument("--pdf-zoom", type=float, default=2.0)
    parser.add_argument("--min-area-ratio", type=float, default=0.003)
    parser.add_argument("--max-area-ratio", type=float, default=0.92)
    parser.add_argument("--merge-iou", type=float, default=0.72)

    parser.add_argument("--text-margin", type=float, default=90.0)
    parser.add_argument("--nearest-text-distance", type=float, default=220.0)
    parser.add_argument("--text-anchor-regions", action="store_true")

    parser.add_argument("--ocr-fallback", action="store_true")
    parser.add_argument("--min-ocr-confidence", type=float, default=20.0)

    parser.add_argument("--svg", action="store_true")

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

    entries = read_jsonl(module_index)

    files = [
        f for f in master.get("files", [])
        if f.get("media_type") in ("image", "document")
    ]

    processed = failed = 0
    total_pages = total_text = total_regions = total_rels = total_crops = total_svgs = 0

    for rec in files:
        print(f"[comic] {root / rec['path']}")
        try:
            result = process_file(rec, root, module_index, entries, run_id, args)
            processed += 1
            total_pages += result["pages"]
            total_text += result["text_objects"]
            total_regions += result["regions"]
            total_rels += result["relationships"]
            total_crops += result["crops"]
            total_svgs += result["svgs"]

            print(f"  module:        {result['module_rel']}")
            print(f"  pages:         {result['pages']}")
            print(f"  text objects:  {result['text_objects']}")
            print(f"  regions:       {result['regions']}")
            print(f"  relationships: {result['relationships']}")
            print(f"  crops:         {result['crops']}")
            print(f"  svgs:          {result['svgs']}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {e}")

    print()
    print("Comic layout module complete.")
    print(f"Run ID:           {run_id}")
    print(f"Files found:      {len(files)}")
    print(f"Processed:        {processed}")
    print(f"Failed:           {failed}")
    print(f"Pages:            {total_pages}")
    print(f"Text objects:     {total_text}")
    print(f"Panel candidates: {total_regions}")
    print(f"Relationships:    {total_rels}")
    print(f"Crops:            {total_crops}")
    print(f"SVGs:             {total_svgs}")
    print(f"Module index:     {module_index}")


if __name__ == "__main__":
    main()
