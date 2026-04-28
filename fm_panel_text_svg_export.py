#!/usr/bin/env python3

import argparse
import base64
import html
import io
import json
from pathlib import Path
from datetime import datetime, timezone

import fitz
from PIL import Image


SCHEMA_VERSION = "0.1.0"
TOOL_NAME = "fm_panel_text_svg_export"
TOOL_VERSION = "0.1.0"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def newest(entries, module_name, fm_id):
    matches = [
        e for e in entries
        if e.get("fm_id") == fm_id and e.get("module_name") == module_name
    ]
    return sorted(matches, key=lambda e: e.get("run_id", ""))[-1] if matches else None


def page_png_b64(pdf_path, page_index, zoom):
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()

    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return base64.b64encode(bio.getvalue()).decode("ascii"), pix.width, pix.height


def scale_bbox(bbox, scale):
    return [float(v) * scale for v in bbox]


def point_in_bbox(x, y, bbox, margin=0):
    x0, y0, x1, y1 = bbox
    return x0 - margin <= x <= x1 + margin and y0 - margin <= y <= y1 + margin


def text_center(line, scale):
    x0, y0, x1, y1 = scale_bbox(line.get("bbox", [0, 0, 0, 0]), scale)
    return (x0 + x1) / 2, (y0 + y1) / 2


def safe_id(value):
    return html.escape(str(value or "").replace(" ", "_"))


def svg_page(width, height, bg_b64, panels, text_lines, text_scale, panel_module_dir):
    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
    )
    out.append(
        f'<image id="page_background" href="data:image/png;base64,{bg_b64}" '
        f'x="0" y="0" width="{width}" height="{height}"/>'
    )

    out.append('<g id="panel_objects" class="panel-objects">')
    for p in panels:
        rid = safe_id(p.get("region_id"))
        bbox = p.get("bbox") or [0, 0, 0, 0]
        x0, y0, x1, y1 = bbox

        crop = p.get("crop") or {}
        crop_path = crop.get("path")
        crop_href = ""

        if crop_path and panel_module_dir:
            crop_file = Path(panel_module_dir) / crop_path
            if crop_file.exists():
                crop_href = html.escape(str(crop_file.resolve()))

        meta = html.escape(json.dumps({
            "region_id": p.get("region_id"),
            "region_type": p.get("region_type"),
            "block_type": p.get("block_type"),
            "asset_type": p.get("asset_type"),
            "bbox": bbox,
            "reading_order": p.get("reading_order"),
            "crop": crop,
            "contains": p.get("contains", [])
        }, ensure_ascii=False))

        out.append(f'<g id="{rid}" class="panel-object" data-region-id="{rid}">')
        out.append(f'<title>{meta}</title>')

        if crop_href:
            out.append(
                f'<image id="{rid}_crop" href="{crop_href}" x="{x0}" y="{y0}" '
                f'width="{x1-x0}" height="{y1-y0}" opacity="1.0"/>'
            )

        out.append('</g>')
    out.append('</g>')

    out.append('<g id="text_line_objects" class="text-line-objects">')
    for line in text_lines:
        txt = html.escape(line.get("text", ""))
        if not txt:
            continue

        bbox = scale_bbox(line.get("bbox", [0, 0, 0, 0]), text_scale)
        x0, y0, x1, y1 = bbox
        tid = safe_id(line.get("id"))
        font_size = max(5, (y1 - y0) * 0.75)

        out.append(f'<g id="{tid}" class="text-line-object">')
        out.append(f'<title>{html.escape(json.dumps(line, ensure_ascii=False))}</title>')
        out.append(
            f'<text x="{x0}" y="{y1}" font-family="Arial, sans-serif" '
            f'font-size="{font_size}" fill="blue">{txt}</text>'
        )
        out.append('</g>')
    out.append('</g>')

    out.append("</svg>")
    return "\n".join(out)


def build_relationships(panels, text_lines, text_scale):
    relationships = []
    panel_text = {p.get("region_id"): [] for p in panels if p.get("region_id")}
    outside_text = []

    for line in text_lines:
        cx, cy = text_center(line, text_scale)
        assigned = []

        for p in panels:
            panel_id = p.get("region_id")
            if not panel_id:
                continue

            if point_in_bbox(cx, cy, p.get("bbox", [0, 0, 0, 0]), margin=2):
                panel_text[panel_id].append(line)
                assigned.append(panel_id)

        if assigned:
            relationships.append({
                "relationship_type": "text_inside_panel",
                "text_id": line.get("id"),
                "panel_ids": assigned,
                "text": line.get("text"),
                "bbox": scale_bbox(line.get("bbox", [0, 0, 0, 0]), text_scale)
            })
        else:
            outside_text.append(line)
            relationships.append({
                "relationship_type": "text_outside_panel",
                "text_id": line.get("id"),
                "panel_ids": [],
                "text": line.get("text"),
                "bbox": scale_bbox(line.get("bbox", [0, 0, 0, 0]), text_scale)
            })

    panel_rows = []
    for p in panels:
        panel_id = p.get("region_id")
        panel_rows.append({
            "panel_id": panel_id,
            "bbox": p.get("bbox"),
            "polygon": p.get("polygon"),
            "reading_order": p.get("reading_order"),
            "crop": p.get("crop"),
            "text_inside": panel_text.get(panel_id, [])
        })

    return panel_rows, outside_text, relationships


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="Clean FileMonster panel + text SVG export: panel image objects plus text line objects, no red outline clutter."
    )
    ap.add_argument("--master", required=True)
    ap.add_argument("--module-index", default=None)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    master_path = Path(args.master).expanduser().resolve()
    master = read_json(master_path)
    root = Path(master["root_path_at_scan"]).expanduser().resolve()

    module_index = (
        Path(args.module_index).expanduser().resolve()
        if args.module_index
        else master_path.parent / "filemonster_module_index.jsonl"
    )

    entries = read_jsonl(module_index)

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    made_svg = 0
    made_json = 0

    for rec in master.get("files", []):
        if rec.get("format") != "pdf":
            continue

        fm_id = rec["fm_id"]
        rel = rec["path"]
        pdf_path = root / rel

        spatial_entry = newest(entries, "spatial_text", fm_id)
        layout_entry = newest(entries, "layout_regions", fm_id)

        if not spatial_entry or not layout_entry:
            print(f"SKIP missing modules: {rel}")
            continue

        spatial = read_json(root / spatial_entry["module_json"])
        layout = read_json(root / layout_entry["module_json"])
        panel_module_dir = (root / layout_entry["module_json"]).parent

        zoom = float(layout.get("data", {}).get("parameters", {}).get("pdf_zoom", 2.0))

        spatial_pages = {p["page"]: p for p in spatial.get("data", {}).get("pages", [])}
        layout_pages = {p["page"]: p for p in layout.get("data", {}).get("pages", [])}

        for page_no, lp in layout_pages.items():
            bg, width, height = page_png_b64(pdf_path, page_no - 1, zoom)

            panels = [
                r for r in lp.get("regions", [])
                if r.get("region_type") in ("panel_candidate", "panel_group", "bounded_quadrilateral")
            ]

            sp = spatial_pages.get(page_no, {})
            lines = sp.get("lines", [])

            panel_rows, outside_text, relationships = build_relationships(panels, lines, zoom)

            svg = svg_page(
                width=width,
                height=height,
                bg_b64=bg,
                panels=panels,
                text_lines=lines,
                text_scale=zoom,
                panel_module_dir=panel_module_dir
            )

            safe_name = Path(rel).name.replace("/", "_")
            base = out_dir / f"{safe_name}.p{page_no:04d}.panel_text_clean"

            svg_path = base.with_suffix(".svg")
            json_path = base.with_suffix(".json")

            svg_path.write_text(svg, encoding="utf-8")

            export_json = {
                "schema": {
                    "name": "FMIAF-panel-text-svg-export",
                    "version": SCHEMA_VERSION
                },
                "record_type": "panel_text_svg_export",
                "created_utc": now_utc(),
                "fm_id": fm_id,
                "ff_id": rec.get("ff_id"),
                "file": rel,
                "page": page_no,
                "svg": str(svg_path),
                "text": {
                    "plain": "\n".join([line.get("text", "") for line in lines if line.get("text")]),
                    "lines": lines,
                    "outside_panels": outside_text
                },
                "panels": panel_rows,
                "relationships": relationships,
                "provenance": {
                    "tool_name": TOOL_NAME,
                    "tool_version": TOOL_VERSION,
                    "source_spatial_text_module": spatial_entry.get("module_json"),
                    "source_layout_regions_module": layout_entry.get("module_json")
                }
            }

            write_json(json_path, export_json)

            made_svg += 1
            made_json += 1
            print(f"WROTE SVG  {svg_path}")
            print(f"WROTE JSON {json_path}")

    print()
    print(f"Clean SVGs written: {made_svg}")
    print(f"Clean JSONs written: {made_json}")
    print(f"Output dir: {out_dir}")


if __name__ == "__main__":
    main()
