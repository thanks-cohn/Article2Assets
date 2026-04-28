#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict


SCHEMA_VERSION = "0.3.0"
TOOL_NAME = "fm_layer_union"
TOOL_VERSION = "0.3.0"


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


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_jsonl(path):
    path = Path(path)
    rows = []
    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                rows.append({
                    "_bad_json_line": line_no,
                    "_error": str(e),
                    "_raw": line
                })
    return rows


def rel_to_root(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except Exception:
        return str(path)


def json_hash(data):
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_layer_id(entry, module_data):
    payload = {
        "fm_id": entry.get("fm_id"),
        "ff_id": entry.get("ff_id"),
        "module_name": entry.get("module_name"),
        "module_json": entry.get("module_json"),
        "run_id": entry.get("run_id") or module_data.get("module", {}).get("run_id"),
        "data_hash": json_hash(module_data),
    }
    return "LAYER:" + json_hash(payload)[:24]


def summarize_module(module_data):
    data = module_data.get("data", {}) if isinstance(module_data, dict) else {}

    text = data.get("text")
    urls = data.get("urls")
    blocks = data.get("blocks")
    regions = data.get("regions")
    relationships = data.get("relationships")

    return {
        "has_data": bool(data),
        "text_chars": len(text.get("plain") or "") if isinstance(text, dict) else 0,
        "url_count": len(urls) if isinstance(urls, list) else 0,
        "block_count": len(blocks) if isinstance(blocks, list) else 0,
        "region_count": len(regions) if isinstance(regions, list) else 0,
        "relationship_count": len(relationships) if isinstance(relationships, list) else 0,
    }


def source_integrity(file_rec, module_data, entry):
    master_sha = file_rec.get("sha256")
    entry_sha = entry.get("source_sha256")
    target = module_data.get("target", {}) if isinstance(module_data, dict) else {}
    module_sha = target.get("source_sha256")
    source_sha = module_sha or entry_sha

    if not master_sha or not source_sha:
        return {
            "known": False,
            "stale": False,
            "reason": "missing_source_sha256",
            "master_sha256": master_sha,
            "module_source_sha256": source_sha,
        }

    return {
        "known": True,
        "stale": master_sha != source_sha,
        "reason": "sha256_mismatch" if master_sha != source_sha else "sha256_match",
        "master_sha256": master_sha,
        "module_source_sha256": source_sha,
    }


def choose_status(redundancy, integrity, requested_status):
    if redundancy == "duplicate_exact":
        return "duplicate"
    if integrity.get("stale"):
        return "source_changed_since_module_run"
    return requested_status


def layer_sort_key(layer):
    run_id = layer.get("run_id") or "no_run_id"
    created = layer.get("created_utc") or ""

    legacy_penalty = 1 if run_id == "no_run_id" else 0

    return (
        legacy_penalty,
        str(run_id),
        str(created)
    )


def build_active_view(layers, include_duplicates=False, include_stale=False):
    layers = sorted(layers, key=layer_sort_key, reverse=False)

    active = {
        "text": {"plain": "", "sources": []},
        "urls": [],
        "blocks": [],
        "regions": [],
        "relationships": [],
        "modules": {},
        "layer_ids_used": []
    }

    seen_text = set()
    seen_urls = set()

    for layer in layers:
        status = layer.get("status")

        if status == "duplicate" and not include_duplicates:
            continue

        if status == "source_changed_since_module_run" and not include_stale:
            continue

        data = layer.get("data", {})
        module_name = layer.get("module_name")
        layer_id = layer.get("layer_id")
        run_id = layer.get("run_id")

        active["layer_ids_used"].append(layer_id)
        active["modules"].setdefault(module_name, []).append(layer_id)

        text = data.get("text")
        if isinstance(text, dict):
            plain = (text.get("plain") or "").strip()
            if plain and plain not in seen_text:
                seen_text.add(plain)
                if active["text"]["plain"]:
                    active["text"]["plain"] += "\n\n"
                active["text"]["plain"] += plain
                active["text"]["sources"].append({
                    "layer_id": layer_id,
                    "module_name": module_name,
                    "run_id": run_id
                })

        urls = data.get("urls")
        if isinstance(urls, list):
            for u in urls:
                url = u.get("url") if isinstance(u, dict) else None
                if not url:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                row = dict(u)
                row["_source_layer"] = layer_id
                row["_source_module"] = module_name
                row["_source_run_id"] = run_id
                active["urls"].append(row)

        blocks = data.get("blocks")
        if isinstance(blocks, list):
            for b in blocks:
                row = dict(b)
                row["_source_layer"] = layer_id
                row["_source_module"] = module_name
                row["_source_run_id"] = run_id
                active["blocks"].append(row)

        regions = data.get("regions")
        if isinstance(regions, list):
            for r in regions:
                row = dict(r)
                row["_source_layer"] = layer_id
                row["_source_module"] = module_name
                row["_source_run_id"] = run_id
                active["regions"].append(row)

        relationships = data.get("relationships")
        if isinstance(relationships, list):
            for rel in relationships:
                row = dict(rel)
                row["_source_layer"] = layer_id
                row["_source_module"] = module_name
                row["_source_run_id"] = run_id
                active["relationships"].append(row)

    return active


def main():
    parser = argparse.ArgumentParser(
        description="FileMonster layer union: append-only, timestamped, stale-aware union view."
    )

    parser.add_argument("--master", required=True)
    parser.add_argument("--module-index", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-file", action="store_true")
    parser.add_argument("--latest-link", action="store_true")
    parser.add_argument("--include-duplicates", action="store_true")
    parser.add_argument("--include-stale", action="store_true")
    parser.add_argument("--status", default="accepted", choices=["accepted", "pending_review"])
    parser.add_argument("--run-id", default=None)

    args = parser.parse_args()

    union_run_id = args.run_id or make_run_id()

    master_path = Path(args.master).expanduser().resolve()
    master = read_json(master_path)
    root = Path(master["root_path_at_scan"]).expanduser().resolve()

    module_index_path = (
        Path(args.module_index).expanduser().resolve()
        if args.module_index
        else master_path.parent / "filemonster_module_index.jsonl"
    )

    output_base = Path(args.output).expanduser().resolve()
    output_path = timestamp_path(output_base, union_run_id).resolve()

    module_entries = read_jsonl(module_index_path)
    entries_by_fm = defaultdict(list)

    bad_index_lines = 0
    for entry in module_entries:
        if "_bad_json_line" in entry:
            bad_index_lines += 1
            continue
        fm_id = entry.get("fm_id")
        if fm_id:
            entries_by_fm[fm_id].append(entry)

    union_files = []
    warnings = []
    conflicts = []

    counts = {
        "layers_total": 0,
        "layers_accepted": 0,
        "layers_duplicate": 0,
        "layers_stale": 0,
        "layers_pending_review": 0,
        "layers_missing_source_sha": 0,
        "files_without_layers": 0,
    }

    for file_rec in master.get("files", []):
        fm_id = file_rec.get("fm_id")
        ff_id = file_rec.get("ff_id")
        rel_file = file_rec.get("path")
        sidecar_rel = file_rec.get("sidecar")

        sidecar_abs = root / sidecar_rel if sidecar_rel else None
        sidecar_loaded = False

        if sidecar_abs and sidecar_abs.exists():
            try:
                read_json(sidecar_abs)
                sidecar_loaded = True
            except Exception as e:
                warnings.append({
                    "type": "sidecar_read_failed",
                    "fm_id": fm_id,
                    "file": rel_file,
                    "sidecar": sidecar_rel,
                    "error": str(e)
                })
        else:
            warnings.append({
                "type": "sidecar_missing",
                "fm_id": fm_id,
                "file": rel_file,
                "sidecar": sidecar_rel
            })

        layers = []
        seen_fingerprints = set()

        for entry in entries_by_fm.get(fm_id, []):
            rel_module = entry.get("module_json")
            module_abs = root / rel_module if rel_module else None

            if not rel_module:
                warnings.append({
                    "type": "module_index_missing_module_json",
                    "fm_id": fm_id,
                    "file": rel_file,
                    "entry": entry
                })
                continue

            if not module_abs.exists():
                warnings.append({
                    "type": "module_json_missing",
                    "fm_id": fm_id,
                    "file": rel_file,
                    "module_json": rel_module
                })
                continue

            try:
                module_data = read_json(module_abs)
            except Exception as e:
                warnings.append({
                    "type": "module_json_read_failed",
                    "fm_id": fm_id,
                    "file": rel_file,
                    "module_json": rel_module,
                    "error": str(e)
                })
                continue

            fingerprint = json_hash(module_data)
            redundancy = "duplicate_exact" if fingerprint in seen_fingerprints else "new"
            seen_fingerprints.add(fingerprint)

            integrity = source_integrity(file_rec, module_data, entry)

            if not integrity.get("known"):
                counts["layers_missing_source_sha"] += 1

            module_name = (
                entry.get("module_name")
                or module_data.get("module", {}).get("name")
                or "unknown"
            )

            run_id = (
                entry.get("run_id")
                or module_data.get("module", {}).get("run_id")
                or "no_run_id"
            )

            layer_id = stable_layer_id(entry, module_data)
            target = module_data.get("target", {}) if isinstance(module_data, dict) else {}

            layer_conflicts = []

            if target.get("fm_id") and target.get("fm_id") != fm_id:
                layer_conflicts.append({
                    "type": "fm_id_mismatch",
                    "master_fm_id": fm_id,
                    "module_fm_id": target.get("fm_id")
                })

            if target.get("ff_id") and target.get("ff_id") != ff_id:
                layer_conflicts.append({
                    "type": "ff_id_mismatch",
                    "master_ff_id": ff_id,
                    "module_ff_id": target.get("ff_id")
                })

            if integrity.get("stale"):
                layer_conflicts.append({
                    "type": "source_sha256_mismatch",
                    "master_sha256": integrity.get("master_sha256"),
                    "module_source_sha256": integrity.get("module_source_sha256")
                })

            for c in layer_conflicts:
                conflicts.append({
                    "fm_id": fm_id,
                    "ff_id": ff_id,
                    "file": rel_file,
                    "layer_id": layer_id,
                    "module_json": rel_module,
                    **c
                })

            status = choose_status(redundancy, integrity, args.status)

            counts["layers_total"] += 1
            if status == "accepted":
                counts["layers_accepted"] += 1
            elif status == "duplicate":
                counts["layers_duplicate"] += 1
            elif status == "source_changed_since_module_run":
                counts["layers_stale"] += 1
            elif status == "pending_review":
                counts["layers_pending_review"] += 1

            layers.append({
                "layer_id": layer_id,
                "fm_id": fm_id,
                "ff_id": ff_id,
                "file": rel_file,
                "module_name": module_name,
                "module_json": rel_module,
                "created_utc": entry.get("created_utc") or module_data.get("module", {}).get("created_utc"),
                "run_id": run_id,
                "source": "module",
                "status": status,
                "redundancy": redundancy,
                "fingerprint_sha256": fingerprint,
                "source_integrity": integrity,
                "summary": summarize_module(module_data),
                "conflicts": layer_conflicts,
                "data": module_data.get("data", {})
            })

        if not layers:
            counts["files_without_layers"] += 1

        active_view = build_active_view(
            layers,
            include_duplicates=args.include_duplicates,
            include_stale=args.include_stale
        )

        file_union = {
            "schema": {"name": "FMIAF-layer-union", "version": SCHEMA_VERSION},
            "record_type": "file_layer_union",
            "created_utc": now_utc(),
            "union_run_id": union_run_id,
            "fm_id": fm_id,
            "ff_id": ff_id,
            "file": rel_file,
            "base": {
                "master": rel_to_root(master_path, root),
                "sidecar": sidecar_rel,
                "sidecar_loaded": sidecar_loaded,
                "sha256": file_rec.get("sha256"),
                "media_type": file_rec.get("media_type"),
                "format": file_rec.get("format"),
                "width": file_rec.get("width"),
                "height": file_rec.get("height"),
                "size_bytes": file_rec.get("size_bytes")
            },
            "layers": [{k: v for k, v in layer.items() if k != "data"} for layer in layers],
            "active_view": active_view,
            "policy": {
                "overwrite_originals": False,
                "append_only_layers": True,
                "union_strategy": "layer_stack_with_clean_active_view",
                "duplicates_in_active_view": bool(args.include_duplicates),
                "stale_layers_in_active_view": bool(args.include_stale),
                "timestamped_outputs": True,
                "latest_link_written": bool(args.latest_link)
            },
            "provenance": {
                "tool_name": TOOL_NAME,
                "tool_version": TOOL_VERSION
            }
        }

        if args.per_file and rel_file:
            per_file_base = root / (rel_file + ".fm.union.json")
            per_file_timestamped = timestamp_path(per_file_base, union_run_id)
            write_json(per_file_timestamped, file_union)
            if args.latest_link:
                write_json(per_file_base, file_union)

        union_files.append(file_union)

    dataset_union = {
        "schema": {"name": "FMIAF-layer-union", "version": SCHEMA_VERSION},
        "record_type": "dataset_layer_union",
        "created_utc": now_utc(),
        "union_run_id": union_run_id,
        "master": rel_to_root(master_path, root),
        "module_index": rel_to_root(module_index_path, root),
        "root_path_at_union": str(root),
        "summary": {
            "files": len(union_files),
            "module_index_entries": len(module_entries),
            "bad_module_index_lines": bad_index_lines,
            "warnings": len(warnings),
            "conflicts": len(conflicts),
            **counts
        },
        "warnings": warnings,
        "conflicts": conflicts,
        "files": union_files,
        "policy": {
            "overwrite_originals": False,
            "append_only_layers": True,
            "timestamped_outputs": True,
            "latest_link_written": bool(args.latest_link),
            "duplicates_in_active_view": bool(args.include_duplicates),
            "stale_layers_in_active_view": bool(args.include_stale)
        },
        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION
        }
    }

    write_json(output_path, dataset_union)

    if args.latest_link:
        write_json(output_base, dataset_union)

    print("Done.")
    print(f"Union run ID:          {union_run_id}")
    print(f"Files united:          {len(union_files)}")
    print(f"Module index entries:  {len(module_entries)}")
    print(f"Bad index lines:       {bad_index_lines}")
    print(f"Layers total:          {counts['layers_total']}")
    print(f"Layers accepted:       {counts['layers_accepted']}")
    print(f"Layers duplicate:      {counts['layers_duplicate']}")
    print(f"Layers stale:          {counts['layers_stale']}")
    print(f"Layers pending review: {counts['layers_pending_review']}")
    print(f"Missing source SHA:    {counts['layers_missing_source_sha']}")
    print(f"Files without layers:  {counts['files_without_layers']}")
    print(f"Warnings:              {len(warnings)}")
    print(f"Conflicts:             {len(conflicts)}")
    print(f"Union JSON:            {output_path}")

    if args.latest_link:
        print(f"Latest union JSON:     {output_base}")

    if args.per_file:
        print("Per-file unions:       enabled")


if __name__ == "__main__":
    main()
