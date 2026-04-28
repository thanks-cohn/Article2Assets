#!/usr/bin/env python3

import argparse, hashlib, json
from pathlib import Path
from datetime import datetime, timezone

SCHEMA_VERSION = "0.2.0"
TOOL_NAME = "fm_export_canonical_dataset"
TOOL_VERSION = "0.2.0"

CATEGORY_MAP = {
    "panel": 1,
    "panel_group": 2,
    "text": 3,
}

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

def sha256_file(path):
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def bbox_xywh(bbox):
    if not bbox or len(bbox) != 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in bbox]
    return [x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)]

def bbox_area(bbox):
    b = bbox_xywh(bbox)
    return 0.0 if not b else float(b[2] * b[3])

def is_group_id(x):
    return bool(x) and str(x).endswith("_GROUP1")

def normalize_asset(crop, source_json_path, src):
    if not isinstance(crop, dict):
        return None

    crop_path = crop.get("path")
    if not crop_path:
        return None

    candidates = []
    raw = Path(crop_path).expanduser()
    if raw.is_absolute():
        candidates.append(raw)

    prov = src.get("provenance", {})
    layout_module = prov.get("source_layout_regions_module")

    if layout_module:
        layout_path = Path(layout_module).expanduser()
        if not layout_path.is_absolute():
            source_file = src.get("file") or ""
            root_guess = Path("/home/papa/Documents/PDF")
            layout_path = root_guess / layout_module
        candidates.append(layout_path.parent / crop_path)

    candidates.append(Path(source_json_path).parent / crop_path)

    final = None
    for c in candidates:
        if c.exists():
            final = c.resolve()
            break

    final = final or candidates[0]

    return {
        "kind": "crop",
        "path": str(final),
        "relative_path": crop_path,
        "sha256": crop.get("sha256") or sha256_file(final),
        "size_bytes": crop.get("size_bytes") or (final.stat().st_size if final.exists() else None),
        "exists": final.exists()
    }

def panel_to_object(panel, source_json_path, src):
    panel_id = panel.get("panel_id") or panel.get("region_id")
    bbox = panel.get("bbox")
    group = is_group_id(panel_id)

    category = "panel_group" if group else "panel"

    return {
        "object_id": panel_id,
        "object_type": "panel_group" if group else "panel",
        "category": category,
        "category_id": CATEGORY_MAP[category],
        "bbox_xyxy": bbox,
        "bbox_xywh": bbox_xywh(bbox),
        "polygon": panel.get("polygon"),
        "area": bbox_area(bbox),
        "reading_order": panel.get("reading_order"),
        "asset": normalize_asset(panel.get("crop"), source_json_path, src),
        "attributes": {
            "is_group": group,
            "assignable": not group,
            "has_crop": bool(panel.get("crop")),
            "text_inside_count_raw": len(panel.get("text_inside", [])) if isinstance(panel.get("text_inside"), list) else 0
        },
        "source": {
            "module": "layout_regions",
            "raw": panel
        }
    }

def text_line_to_object(line, index):
    text_id = line.get("id") or f"TEXT_LINE_{index}"
    bbox = line.get("bbox")

    return {
        "object_id": text_id,
        "object_type": "text_line",
        "category": "text",
        "category_id": CATEGORY_MAP["text"],
        "text": line.get("text", ""),
        "bbox_xyxy": bbox,
        "bbox_xywh": bbox_xywh(bbox),
        "polygon": None,
        "area": bbox_area(bbox),
        "reading_order": index,
        "attributes": {
            "block_no": line.get("block_no"),
            "page": line.get("page")
        },
        "source": {
            "module": "spatial_text",
            "raw": line
        }
    }

def clean_relationships(raw_relationships, panel_objects):
    panel_area = {
        p["object_id"]: p.get("area", 0)
        for p in panel_objects
        if p.get("object_id")
    }

    grouped = {}

    for rel in raw_relationships:
        text_id = rel.get("text_id")
        if not text_id:
            continue

        panel_ids = rel.get("panel_ids", [])
        if not panel_ids and rel.get("to_object_id"):
            panel_ids = [rel.get("to_object_id")]

        if not panel_ids:
            grouped.setdefault(text_id, {
                "text": rel.get("text"),
                "bbox": rel.get("bbox"),
                "panel_ids": []
            })
            continue

        g = grouped.setdefault(text_id, {
            "text": rel.get("text"),
            "bbox": rel.get("bbox"),
            "panel_ids": []
        })

        for pid in panel_ids:
            if pid not in g["panel_ids"]:
                g["panel_ids"].append(pid)

    out = []

    for text_id, item in grouped.items():
        ids = item["panel_ids"]
        real = [pid for pid in ids if not is_group_id(pid)]
        groups = [pid for pid in ids if is_group_id(pid)]

        if real:
            best = sorted(real, key=lambda pid: panel_area.get(pid, float("inf")))[0]
            out.append({
                "relationship_type": "text_inside_panel",
                "from_object_id": text_id,
                "to_object_id": best,
                "text": item.get("text"),
                "bbox_xyxy": item.get("bbox"),
                "assignment_policy": "smallest_assignable_panel_wins",
                "discarded_container_ids": groups,
                "discarded_overlapping_panel_ids": [pid for pid in real if pid != best]
            })
        elif groups:
            out.append({
                "relationship_type": "text_inside_panel_group",
                "from_object_id": text_id,
                "to_object_id": groups[0],
                "text": item.get("text"),
                "bbox_xyxy": item.get("bbox"),
                "assignment_policy": "group_only_no_assignable_panel"
            })
        else:
            out.append({
                "relationship_type": "text_outside_panel",
                "from_object_id": text_id,
                "to_object_id": None,
                "text": item.get("text"),
                "bbox_xyxy": item.get("bbox"),
                "assignment_policy": "no_panel_contains_text"
            })

    return out

def infer_page_size(objects):
    max_x = 0.0
    max_y = 0.0
    for obj in objects:
        b = obj.get("bbox_xyxy")
        if b and len(b) == 4:
            max_x = max(max_x, float(b[2]))
            max_y = max(max_y, float(b[3]))
    return max_x or None, max_y or None

def canonical_record(source_json_path):
    src = read_json(source_json_path)

    text = src.get("text", {})
    panels = src.get("panels", [])
    lines = text.get("lines", [])
    relationships_raw = src.get("relationships", [])

    panel_objects = [panel_to_object(p, source_json_path, src) for p in panels]
    text_objects = [text_line_to_object(line, i + 1) for i, line in enumerate(lines)]
    objects = panel_objects + text_objects

    relationships = clean_relationships(relationships_raw, panel_objects)

    page_w, page_h = infer_page_size(objects)

    categories = [
        {"id": 1, "name": "panel", "supercategory": "layout"},
        {"id": 2, "name": "panel_group", "supercategory": "layout"},
        {"id": 3, "name": "text", "supercategory": "text"},
    ]

    page_id = f"{src.get('fm_id')}:p{int(src.get('page', 0)):04d}"

    return {
        "schema": {
            "name": "FMIAF-canonical-page-record",
            "version": SCHEMA_VERSION
        },
        "record_type": "canonical_page_record",
        "created_utc": now_utc(),

        "ids": {
            "fm_id": src.get("fm_id"),
            "ff_id": src.get("ff_id"),
            "page_id": page_id,
            "source_file": src.get("file"),
            "source_json": str(Path(source_json_path).expanduser().resolve())
        },

        "page": {
            "page_number": src.get("page"),
            "svg": src.get("svg"),
            "width": page_w,
            "height": page_h,
            "page_image": None
        },

        "categories": categories,

        "text": {
            "plain": text.get("plain", ""),
            "line_count": len(lines),
            "lines": lines,
            "outside_panels_raw": text.get("outside_panels", [])
        },

        "objects": objects,
        "object_counts": {
            "total": len(objects),
            "panels": len([o for o in panel_objects if o["object_type"] == "panel"]),
            "panel_groups": len([o for o in panel_objects if o["object_type"] == "panel_group"]),
            "text_lines": len(text_objects)
        },

        "relationships": relationships,
        "relationship_counts": {
            "total": len(relationships),
            "text_inside_panel": len([r for r in relationships if r["relationship_type"] == "text_inside_panel"]),
            "text_inside_panel_group": len([r for r in relationships if r["relationship_type"] == "text_inside_panel_group"]),
            "text_outside_panel": len([r for r in relationships if r["relationship_type"] == "text_outside_panel"])
        },

        "quality": {
            "conversion_ready": True,
            "has_objects": bool(objects),
            "has_text": bool(text.get("plain")),
            "has_panels": any(o["object_type"] == "panel" for o in objects),
            "has_relationships": bool(relationships),
            "group_relationships_are_containers_only": True
        },

        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "source_panel_text_export": str(Path(source_json_path).expanduser().resolve()),
            "source_panel_text_provenance": src.get("provenance", {})
        }
    }

def main():
    ap = argparse.ArgumentParser(description="Export FileMonster panel/text JSON into conversion-ready canonical JSONL.")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-jsonl", required=True)
    ap.add_argument("--output-json", default=None)
    ap.add_argument("--glob", default="*.json")
    args = ap.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    json_files = sorted(input_dir.glob(args.glob))

    rows, skipped = [], []

    for path in json_files:
        try:
            rows.append(canonical_record(path))
        except Exception as e:
            skipped.append({"path": str(path), "error": str(e)})

    write_jsonl(args.output_jsonl, rows)

    summary = {
        "schema": {
            "name": "FMIAF-canonical-dataset-summary",
            "version": SCHEMA_VERSION
        },
        "record_type": "canonical_dataset_summary",
        "created_utc": now_utc(),
        "input_dir": str(input_dir),
        "input_glob": args.glob,
        "rows_written": len(rows),
        "skipped": len(skipped),
        "skipped_records": skipped,
        "totals": {
            "objects": sum(r["object_counts"]["total"] for r in rows),
            "panels": sum(r["object_counts"]["panels"] for r in rows),
            "panel_groups": sum(r["object_counts"]["panel_groups"] for r in rows),
            "text_lines": sum(r["object_counts"]["text_lines"] for r in rows),
            "relationships": sum(r["relationship_counts"]["total"] for r in rows),
            "text_inside_panel": sum(r["relationship_counts"]["text_inside_panel"] for r in rows),
            "text_inside_panel_group": sum(r["relationship_counts"]["text_inside_panel_group"] for r in rows),
            "text_outside_panel": sum(r["relationship_counts"]["text_outside_panel"] for r in rows),
            "text_chars": sum(len(r["text"]["plain"]) for r in rows)
        },
        "output_jsonl": str(Path(args.output_jsonl).expanduser().resolve()),
        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION
        }
    }

    if args.output_json:
        write_json(args.output_json, summary)

    print("Canonical dataset export complete.")
    print(f"Input JSON files:        {len(json_files)}")
    print(f"Rows written:            {len(rows)}")
    print(f"Skipped:                 {len(skipped)}")
    print(f"Objects:                 {summary['totals']['objects']}")
    print(f"Panels:                  {summary['totals']['panels']}")
    print(f"Panel groups:            {summary['totals']['panel_groups']}")
    print(f"Text lines:              {summary['totals']['text_lines']}")
    print(f"Relationships:           {summary['totals']['relationships']}")
    print(f"Text inside panels:      {summary['totals']['text_inside_panel']}")
    print(f"Text inside groups only: {summary['totals']['text_inside_panel_group']}")
    print(f"Text outside panels:     {summary['totals']['text_outside_panel']}")
    print(f"JSONL:                   {args.output_jsonl}")
    if args.output_json:
        print(f"Summary JSON:            {args.output_json}")

if __name__ == "__main__":
    main()
