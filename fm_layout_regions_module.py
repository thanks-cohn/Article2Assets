#!/usr/bin/env python3

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
from datetime import datetime, timezone

import fitz
import cv2
import numpy as np
from PIL import Image


SCHEMA_VERSION = "0.4.0"
TOOL_NAME = "fm_layout_regions_module"
TOOL_VERSION = "0.4.0"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def make_run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_jsonl(path, row):
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


def image_to_array(path):
    return np.array(Image.open(path).convert("RGB"))


def render_pdf_page(path, page_index, zoom=2.0):
    doc = fitz.open(path)
    page = doc[page_index]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    doc.close()
    return arr, float(pix.width), float(pix.height)


def load_pages_for_file(path, fmt, pdf_zoom):
    if fmt == "pdf" or str(path).lower().endswith(".pdf"):
        doc = fitz.open(path)
        n = len(doc)
        doc.close()
        return [(i + 1, *render_pdf_page(path, i, pdf_zoom)) for i in range(n)]

    arr = image_to_array(path)
    h, w = arr.shape[:2]
    return [(1, arr, float(w), float(h))]


def bbox_from_poly(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]


def polygon_area(poly):
    return float(abs(cv2.contourArea(np.array(poly, dtype=np.float32))))


def normalize_polygon(poly):
    pts = sorted(poly, key=lambda p: (p[1], p[0]))
    top = sorted(pts[:2], key=lambda p: p[0])
    bottom = sorted(pts[2:], key=lambda p: p[0])
    return [
        [float(top[0][0]), float(top[0][1])],
        [float(top[1][0]), float(top[1][1])],
        [float(bottom[1][0]), float(bottom[1][1])],
        [float(bottom[0][0]), float(bottom[0][1])]
    ]


def iou_bbox(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b

    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)

    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area_a = max(0, ax1 - ax0) * max(0, ay1 - ay0)
    area_b = max(0, bx1 - bx0) * max(0, by1 - by0)
    union = area_a + area_b - inter
    return 0.0 if union <= 0 else inter / union


def contains_bbox(parent, child, margin=0):
    px0, py0, px1, py1 = parent
    cx0, cy0, cx1, cy1 = child
    return (
        cx0 >= px0 - margin and
        cy0 >= py0 - margin and
        cx1 <= px1 + margin and
        cy1 <= py1 + margin
    )


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
    Image.fromarray(crop).save(path)
    data = path.read_bytes()
    return {
        "path": path.name,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data)
    }


def arr_to_png_base64(arr):
    import io
    bio = io.BytesIO()
    Image.fromarray(arr).save(bio, format="PNG")
    return base64.b64encode(bio.getvalue()).decode("ascii")


def profile_passes(profile):
    if profile == "strict":
        return [
            {"name": "large_strict", "min_area_ratio": 0.006, "epsilon_ratio": 0.025, "canny1": 55, "canny2": 170, "dilate": 1},
            {"name": "medium_strict", "min_area_ratio": 0.002, "epsilon_ratio": 0.020, "canny1": 45, "canny2": 140, "dilate": 1},
        ]

    if profile == "comic":
        return [
            {"name": "large_panels", "min_area_ratio": 0.004, "epsilon_ratio": 0.028, "canny1": 45, "canny2": 150, "dilate": 1},
            {"name": "medium_panels", "min_area_ratio": 0.001, "epsilon_ratio": 0.018, "canny1": 30, "canny2": 110, "dilate": 2},
            {"name": "small_panels", "min_area_ratio": 0.00025, "epsilon_ratio": 0.012, "canny1": 20, "canny2": 85, "dilate": 2},
            {"name": "thin_edges", "min_area_ratio": 0.00020, "epsilon_ratio": 0.010, "canny1": 12, "canny2": 60, "dilate": 1},
        ]

    if profile == "article":
        return [
            {"name": "article_blocks", "min_area_ratio": 0.003, "epsilon_ratio": 0.025, "canny1": 40, "canny2": 145, "dilate": 1},
            {"name": "small_callouts", "min_area_ratio": 0.0007, "epsilon_ratio": 0.016, "canny1": 25, "canny2": 100, "dilate": 2},
        ]

    return [
        {"name": "large", "min_area_ratio": 0.004, "epsilon_ratio": 0.025, "canny1": 45, "canny2": 155, "dilate": 1},
        {"name": "medium", "min_area_ratio": 0.001, "epsilon_ratio": 0.018, "canny1": 30, "canny2": 110, "dilate": 2},
        {"name": "small", "min_area_ratio": 0.00035, "epsilon_ratio": 0.012, "canny1": 20, "canny2": 90, "dilate": 2},
    ]


def detect_regions_one_pass(arr, pass_cfg, max_area_ratio):
    h, w = arr.shape[:2]
    page_area = w * h

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(blur, pass_cfg["canny1"], pass_cfg["canny2"])
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=pass_cfg["dilate"])

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []

    for c in contours:
        raw_area = cv2.contourArea(c)

        if raw_area < page_area * pass_cfg["min_area_ratio"]:
            continue
        if raw_area > page_area * max_area_ratio:
            continue

        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, pass_cfg["epsilon_ratio"] * peri, True)

        if len(approx) != 4:
            x, y, bw, bh = cv2.boundingRect(c)
            if bw < 20 or bh < 20:
                continue
            poly = [[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]]
            approx_kind = "bounding_rect_fallback"
        else:
            poly = [[float(p[0][0]), float(p[0][1])] for p in approx]
            poly = normalize_polygon(poly)
            approx_kind = "quadrilateral"

        bbox = bbox_from_poly(poly)
        x0, y0, x1, y1 = bbox
        bw = x1 - x0
        bh = y1 - y0

        if bw < 20 or bh < 20:
            continue

        reg_area = polygon_area(poly)
        rectangularity = reg_area / max(1.0, bw * bh)

        if rectangularity < 0.55:
            continue

        regions.append({
            "polygon": poly,
            "bbox": bbox,
            "area": reg_area,
            "area_ratio": float(reg_area / page_area),
            "rectangularity": float(rectangularity),
            "confidence": float(min(1.0, rectangularity)),
            "region_type": "panel_candidate",
            "block_type": "layout_region",
            "asset_type": "panel_crop",
            "detector_pass": pass_cfg["name"],
            "approximation": approx_kind
        })

    return regions


def merge_regions(regions, iou_threshold=0.82):
    kept = []

    for r in sorted(regions, key=lambda x: (x["area"], x["confidence"]), reverse=True):
        duplicate = False
        for k in kept:
            if iou_bbox(r["bbox"], k["bbox"]) >= iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(r)

    return sorted(kept, key=lambda r: (r["bbox"][1], r["bbox"][0]))


def remove_outer_page_region(regions, width, height, cutoff=0.93):
    page_bbox = [0, 0, width, height]
    out = []
    for r in regions:
        if r["area_ratio"] > cutoff and iou_bbox(r["bbox"], page_bbox) > 0.80:
            continue
        out.append(r)
    return out


def detect_regions(arr, profile, max_area_ratio, merge_iou):
    regions = []
    for cfg in profile_passes(profile):
        regions.extend(detect_regions_one_pass(arr, cfg, max_area_ratio=max_area_ratio))

    h, w = arr.shape[:2]
    regions = remove_outer_page_region(regions, w, h)
    regions = merge_regions(regions, iou_threshold=merge_iou)

    for i, r in enumerate(regions, start=1):
        r["reading_order"] = i

    return regions


def make_group_region(page_no, regions, arr, module_dir, run_id, crop_group):
    if not regions:
        return None

    xs0 = [r["bbox"][0] for r in regions]
    ys0 = [r["bbox"][1] for r in regions]
    xs1 = [r["bbox"][2] for r in regions]
    ys1 = [r["bbox"][3] for r in regions]

    bbox = [min(xs0), min(ys0), max(xs1), max(ys1)]
    polygon = [
        [bbox[0], bbox[1]],
        [bbox[2], bbox[1]],
        [bbox[2], bbox[3]],
        [bbox[0], bbox[3]]
    ]

    group = {
        "region_id": f"P{page_no}_GROUP1",
        "page": page_no,
        "polygon": polygon,
        "bbox": bbox,
        "area": polygon_area(polygon),
        "area_ratio": polygon_area(polygon) / max(1, arr.shape[0] * arr.shape[1]),
        "rectangularity": 1.0,
        "confidence": 1.0,
        "region_type": "panel_group",
        "block_type": "layout_region_group",
        "asset_type": "panel_group_crop",
        "reading_order": 0,
        "contains": [r["region_id"] for r in regions]
    }

    if crop_group:
        crop = crop_region(arr, bbox)
        if crop is not None:
            crop_name = f"layout_regions.{run_id}.{group['region_id']}.png"
            group["crop"] = save_crop_png(crop, module_dir / crop_name)
        else:
            group["crop"] = None
    else:
        group["crop"] = None

    return group


def region_to_block(region):
    return {
        "block_id": region["region_id"],
        "block_type": region.get("block_type", "layout_region"),
        "region_type": region.get("region_type"),
        "asset_type": region.get("asset_type"),
        "page": region["page"],
        "bbox": region["bbox"],
        "polygon": region["polygon"],
        "reading_order": region.get("reading_order"),
        "confidence": region.get("confidence"),
        "area": region.get("area"),
        "area_ratio": region.get("area_ratio"),
        "rectangularity": region.get("rectangularity"),
        "crop": region.get("crop"),
        "contains": region.get("contains", []),
        "parent_region_id": region.get("parent_region_id"),
        "label": region.get("region_type", "layout_region")
    }


def svg_page(width, height, page_png_b64, regions, embed_page_background):
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )

    if embed_page_background and page_png_b64:
        parts.append(
            f'<image id="page_image" href="data:image/png;base64,{page_png_b64}" '
            f'x="0" y="0" width="{width}" height="{height}"/>'
        )
    else:
        parts.append('<rect id="page_background" x="0" y="0" width="100%" height="100%" fill="white"/>')

    parts.append('<g id="layout_regions" class="layout-regions panel-assets">')

    for r in regions:
        rid = html.escape(r["region_id"])
        pts = " ".join(f"{x},{y}" for x, y in r["polygon"])
        x0, y0, x1, y1 = r["bbox"]
        crop = r.get("crop") or {}
        crop_href = html.escape(crop.get("path", ""))
        stroke = "blue" if r.get("region_type") == "panel_group" else "red"
        width_stroke = "4" if r.get("region_type") == "panel_group" else "3"

        meta = html.escape(json.dumps({
            "region_id": r["region_id"],
            "block_type": r.get("block_type"),
            "region_type": r.get("region_type"),
            "asset_type": r.get("asset_type"),
            "page": r.get("page"),
            "bbox": r.get("bbox"),
            "polygon": r.get("polygon"),
            "reading_order": r.get("reading_order"),
            "confidence": r.get("confidence"),
            "crop": r.get("crop"),
            "contains": r.get("contains", [])
        }, ensure_ascii=False))

        parts.append(f'  <g id="{rid}" class="layout-region {html.escape(r.get("region_type", ""))}" data-region-id="{rid}">')
        parts.append(f'    <title>{meta}</title>')

        if crop_href:
            parts.append(
                f'    <image id="{rid}_image" href="{crop_href}" x="{x0}" y="{y0}" '
                f'width="{x1-x0}" height="{y1-y0}" opacity="1.0"/>'
            )

        parts.append(
            f'    <polygon id="{rid}_polygon" points="{pts}" '
            f'fill="none" stroke="{stroke}" stroke-width="{width_stroke}" opacity="0.95"/>'
        )

        parts.append(
            f'    <text id="{rid}_label" x="{x0}" y="{max(14, y0 - 6)}" '
            f'font-family="Arial, sans-serif" font-size="14" fill="{stroke}">{rid}</text>'
        )
        parts.append("  </g>")

    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def process_file(rec, root, module_index, run_id, args):
    rel = rec["path"]
    fmt = rec.get("format", "")
    src_path = root / rel

    module_dir_rel = rec.get("module_output_directory", rel + ".fm.modules")
    module_dir = root / module_dir_rel
    module_dir.mkdir(parents=True, exist_ok=True)

    source_sha = sha256_file(src_path)
    pages = load_pages_for_file(src_path, fmt, args.pdf_zoom)

    pages_out = []
    svg_files = []

    for page_no, arr, width, height in pages:
        regions = detect_regions(
            arr,
            profile=args.profile,
            max_area_ratio=args.max_area_ratio,
            merge_iou=args.merge_iou
        )

        for i, r in enumerate(regions, start=1):
            r["region_id"] = f"P{page_no}_R{i}"
            r["page"] = page_no
            r["parent_region_id"] = f"P{page_no}_GROUP1" if args.crop_panel_group else None

            if args.crop_panels:
                crop = crop_region(arr, r["bbox"])
                if crop is not None:
                    crop_name = f"layout_regions.{run_id}.{r['region_id']}.png"
                    r["crop"] = save_crop_png(crop, module_dir / crop_name)
                else:
                    r["crop"] = None
            else:
                r["crop"] = None

        group_region = make_group_region(
            page_no,
            regions,
            arr,
            module_dir,
            run_id,
            crop_group=args.crop_panel_group
        ) if args.crop_panel_group else None

        all_page_regions = ([group_region] if group_region else []) + regions
        blocks = [region_to_block(r) for r in all_page_regions]

        page_obj = {
            "page": page_no,
            "width": width,
            "height": height,
            "region_count": len(all_page_regions),
            "panel_count": len(regions),
            "group_count": 1 if group_region else 0,
            "block_count": len(blocks),
            "regions": all_page_regions,
            "blocks": blocks
        }

        if args.svg:
            page_png_b64 = arr_to_png_base64(arr) if args.embed_page_background else None
            svg_name = f"layout_regions.{run_id}.p{page_no:04d}.svg"
            (module_dir / svg_name).write_text(
                svg_page(width, height, page_png_b64, all_page_regions, args.embed_page_background),
                encoding="utf-8"
            )
            svg_files.append(svg_name)
            page_obj["svg"] = svg_name

        pages_out.append(page_obj)

    all_regions = [r for p in pages_out for r in p["regions"]]
    all_blocks = [b for p in pages_out for b in p["blocks"]]
    crop_files = [r["crop"] for r in all_regions if r.get("crop")]

    module_name = f"layout_regions.{run_id}.json"
    module_path = module_dir / module_name
    module_rel = str(Path(module_dir_rel) / module_name)

    module_json = {
        "schema": {"name": "FMIAF-module", "version": SCHEMA_VERSION},
        "record_type": "module_output",
        "module": {
            "name": "layout_regions",
            "version": TOOL_VERSION,
            "engine": "opencv_multipass_quad_detector_with_panel_assets",
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
            "suggested_target": "modules.layout_regions",
            "merge_strategy": "pointer_append",
            "overwrite_originals": False
        },
        "data": {
            "success": True,
            "source": "rendered_page_edges",
            "region_family": "bounded_quadrilateral",
            "asset_family": "panel_crop",
            "svg_pages": svg_files,
            "crop_files": crop_files,
            "parameters": {
                "profile": args.profile,
                "pdf_zoom": args.pdf_zoom,
                "max_area_ratio": args.max_area_ratio,
                "merge_iou": args.merge_iou,
                "crop_panels": args.crop_panels,
                "crop_panel_group": args.crop_panel_group,
                "svg": args.svg,
                "embed_page_background": args.embed_page_background
            },
            "pages": pages_out,
            "regions": all_regions,
            "blocks": all_blocks
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
        "module_name": "layout_regions",
        "module_json": module_rel,
        "suggested_target": "modules.layout_regions",
        "merge_strategy": "pointer_append",
        "run_id": run_id,
        "append_only": True,
        "source_sha256": source_sha,
        "tool_name": TOOL_NAME,
        "tool_version": TOOL_VERSION
    })

    return {
        "module_rel": module_rel,
        "pages": len(pages_out),
        "regions": len(all_regions),
        "blocks": len(all_blocks),
        "crops": len(crop_files),
        "svgs": len(svg_files)
    }


def main():
    parser = argparse.ArgumentParser(
        description="FileMonster layout regions v0.4: recall-first panel/region detector with individual and grouped panel assets."
    )

    parser.add_argument("--master", required=True)
    parser.add_argument("--module-index", default=None)
    parser.add_argument("--run-id", default=None)

    parser.add_argument("--profile", default="balanced", choices=["strict", "balanced", "recall", "comic", "article"])
    parser.add_argument("--pdf-zoom", type=float, default=2.0)
    parser.add_argument("--max-area-ratio", type=float, default=0.95)
    parser.add_argument("--merge-iou", type=float, default=0.82)

    parser.add_argument("--crop-panels", action="store_true")
    parser.add_argument("--crop-panel-group", action="store_true")
    parser.add_argument("--svg", action="store_true")
    parser.add_argument("--embed-page-background", action="store_true")

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

    files = [
        f for f in master.get("files", [])
        if f.get("media_type") in ("image", "document")
    ]

    processed = failed = 0
    total_regions = total_blocks = total_crops = total_svgs = 0

    for rec in files:
        print(f"[layout] {root / rec['path']}")
        try:
            result = process_file(rec, root, module_index, run_id, args)
            processed += 1
            total_regions += result["regions"]
            total_blocks += result["blocks"]
            total_crops += result["crops"]
            total_svgs += result["svgs"]

            print(f"  module:  {result['module_rel']}")
            print(f"  pages:   {result['pages']}")
            print(f"  regions: {result['regions']}")
            print(f"  blocks:  {result['blocks']}")
            print(f"  crops:   {result['crops']}")
            print(f"  svgs:    {result['svgs']}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {e}")

    print()
    print("Layout regions module complete.")
    print(f"Run ID:        {run_id}")
    print(f"Profile:       {args.profile}")
    print(f"Files found:   {len(files)}")
    print(f"Processed:     {processed}")
    print(f"Failed:        {failed}")
    print(f"Total regions: {total_regions}")
    print(f"Total blocks:  {total_blocks}")
    print(f"Total crops:   {total_crops}")
    print(f"Total SVGs:    {total_svgs}")
    print(f"Module index:  {module_index}")


if __name__ == "__main__":
    main()
