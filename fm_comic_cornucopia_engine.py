#!/usr/bin/env python3
"""
FileMonster Comic Cornucopia Engine v0.1

Single unified engine for:
- PDF / image / directory input
- text extraction (spatial + OCR fallback)
- panel detection
- region extraction (including unknown regions)
- relationships
- SVG generation
- JSON + JSONL dataset output

Designed to be called by comic_gui.py OR CLI.
"""

import argparse
import json
from pathlib import Path
from datetime import datetime

# Import your existing modules (organs)
from fm_spatial_text_module import extract_pdf_spatial
from fm_comic_panel_detector import load_pages, detect_border_boxes, detect_white_panel_interiors, detect_art_masses
from fm_panel_text_svg_export import svg_page, build_relationships
from fm_export_canonical_dataset import canonical_record


# ----------------------------
# Utilities
# ----------------------------

def now():
    return datetime.utcnow().isoformat()

def log(msg, callback=None):
    if callback:
        callback(msg)
    else:
        print(msg)


# ----------------------------
# Core Engine
# ----------------------------

class ComicCornucopiaEngine:

    def __init__(self, input_path, output_dir, options=None, log_callback=None):
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.options = options or {}
        self.log_callback = log_callback

        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------
    # Main runner
    # ----------------------------

    def run(self):
        log("🌱 Starting Cornucopia Engine...", self.log_callback)

        pages = self._load_input()

        dataset = []

        for page_no, arr, width, height in pages:
            log(f"Processing page {page_no}", self.log_callback)

            text_lines = self._extract_text(page_no)
            panels = self._detect_panels(arr, width, height)

            # fallback: create unknown regions if nothing detected
            if not panels:
                panels = self._fallback_regions(width, height)

            panel_rows, outside_text, relationships = build_relationships(
                panels, text_lines, text_scale=1.0
            )

            svg_path = self._write_svg(page_no, arr, panels, text_lines, width, height)
            json_path = self._write_page_json(page_no, panel_rows, text_lines, relationships)

            dataset.append(json_path)

        self._write_dataset(dataset)

        log("🌌 Cornucopia complete.", self.log_callback)

    # ----------------------------
    # Input Handling
    # ----------------------------

    def _load_input(self):
        if self.input_path.is_dir():
            images = list(self.input_path.glob("*"))
            pages = []
            for i, img in enumerate(images, start=1):
                arr, w, h = load_pages(img, "image", 1.0)[0][1:]
                pages.append((i, arr, w, h))
            return pages

        else:
            return load_pages(self.input_path, "pdf", 2.0)

    # ----------------------------
    # Text
    # ----------------------------

    def _extract_text(self, page_no):
        try:
            spatial = extract_pdf_spatial(self.input_path, "line")
            pages = spatial.get("pages", [])
            for p in pages:
                if p["page"] == page_no:
                    return p.get("lines", [])
        except Exception:
            return []

    # ----------------------------
    # Panels / Regions
    # ----------------------------

    def _detect_panels(self, arr, width, height):
        border = detect_border_boxes(arr, self._args())
        white = detect_white_panel_interiors(arr, self._args())
        art = detect_art_masses(arr, self._args())

        regions = border + white + art

        # assign IDs
        for i, r in enumerate(regions, start=1):
            r["region_id"] = f"P{i}"
            r["bbox"] = r["bbox"]

        return regions

    def _fallback_regions(self, width, height):
        return [{
            "region_id": "fallback_1",
            "bbox": [0, 0, width, height],
            "polygon": [[0,0],[width,0],[width,height],[0,height]],
            "region_type": "unknown_visual_region"
        }]

    def _args(self):
        class Args:
            min_area_ratio = 0.002
            max_area_ratio = 0.95
            min_side = 40
            white_threshold = 240
            gutter_close_kernel = 7
            art_threshold = 240
        return Args()

    # ----------------------------
    # SVG + JSON
    # ----------------------------

    def _write_svg(self, page_no, arr, panels, text_lines, width, height):
        svg_dir = self.output_dir / "svg"
        svg_dir.mkdir(exist_ok=True)

        svg_content = svg_page(
            width, height,
            bg_b64="",  # optional: embed image later
            panels=panels,
            text_lines=text_lines,
            text_scale=1.0,
            panel_module_dir=None
        )

        path = svg_dir / f"page_{page_no:04d}.svg"
        path.write_text(svg_content, encoding="utf-8")
        return path

    def _write_page_json(self, page_no, panels, text_lines, relationships):
        json_dir = self.output_dir / "page_json"
        json_dir.mkdir(exist_ok=True)

        data = {
            "page": page_no,
            "panels": panels,
            "text": text_lines,
            "relationships": relationships,
            "created": now()
        }

        path = json_dir / f"page_{page_no:04d}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def _write_dataset(self, page_json_paths):
        dataset_path = self.output_dir / "dataset.jsonl"

        with dataset_path.open("w", encoding="utf-8") as f:
            for p in page_json_paths:
                rec = canonical_record(str(p))
                f.write(json.dumps(rec) + "\n")


# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(description="FileMonster Comic Cornucopia Engine")

    parser.add_argument("input", help="PDF / image / directory")
    parser.add_argument("--out", required=True)

    args = parser.parse_args()

    engine = ComicCornucopiaEngine(
        input_path=args.input,
        output_dir=args.out
    )

    engine.run()


if __name__ == "__main__":
    main()
