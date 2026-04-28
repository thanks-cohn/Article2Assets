#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


SCHEMA_VERSION = "0.1.0"
TOOL_NAME = "fm_snapshot_manifest"
TOOL_VERSION = "0.1.0"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def make_snapshot_id():
    return datetime.now(timezone.utc).strftime("FMSNAP:%Y%m%dT%H%M%SZ")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    path = Path(path).expanduser().resolve()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_jsonl(path):
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return None
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def file_record(path, kind):
    path = Path(path).expanduser().resolve()

    if not path.exists():
        return {
            "kind": kind,
            "path": str(path),
            "exists": False
        }

    rec = {
        "kind": kind,
        "path": str(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path)
    }

    if path.suffix.lower() == ".jsonl":
        rec["jsonl_rows"] = count_jsonl(path)

    return rec


def write_json(path, data):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Create an immutable FileMonster dataset snapshot manifest."
    )

    parser.add_argument("--master", required=True)
    parser.add_argument("--union", required=True)
    parser.add_argument("--audit", default=None)
    parser.add_argument("--validation", default=None)
    parser.add_argument("--training-export", default=None)
    parser.add_argument("--url-index", default=None)
    parser.add_argument("--text-index", default=None)
    parser.add_argument("--ocr-research-json", default=None)
    parser.add_argument("--ocr-pdf", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument("--notes", default=None)

    args = parser.parse_args()

    snapshot_id = args.snapshot_id or make_snapshot_id()

    master_path = Path(args.master).expanduser().resolve()
    union_path = Path(args.union).expanduser().resolve()

    master = read_json(master_path)
    union = read_json(union_path)

    artifacts = [
        file_record(master_path, "master_ledger"),
        file_record(union_path, "layer_union"),
    ]

    optional = [
        (args.audit, "audit_report"),
        (args.validation, "validation_report"),
        (args.training_export, "training_export_jsonl"),
        (args.url_index, "url_index_jsonl"),
        (args.text_index, "text_index_jsonl"),
        (args.ocr_research_json, "ocr_research_json"),
        (args.ocr_pdf, "ocr_clickable_pdf"),
    ]

    for path, kind in optional:
        if path:
            artifacts.append(file_record(path, kind))

    missing = [a for a in artifacts if not a.get("exists")]

    summary = {
        "files_in_master": len(master.get("files", [])),
        "files_in_union": len(union.get("files", [])),
        "union_run_id": union.get("union_run_id"),
        "missing_artifacts": len(missing),
        "artifact_count": len(artifacts),
    }

    for a in artifacts:
        if a.get("kind") == "training_export_jsonl":
            summary["training_export_rows"] = a.get("jsonl_rows")
        if a.get("kind") == "url_index_jsonl":
            summary["url_index_rows"] = a.get("jsonl_rows")
        if a.get("kind") == "text_index_jsonl":
            summary["text_index_rows"] = a.get("jsonl_rows")

    manifest_core = {
        "snapshot_id": snapshot_id,
        "union_run_id": union.get("union_run_id"),
        "master_sha256": artifacts[0].get("sha256"),
        "union_sha256": artifacts[1].get("sha256"),
        "artifact_hashes": [
            {
                "kind": a.get("kind"),
                "path": a.get("path"),
                "sha256": a.get("sha256")
            }
            for a in artifacts
            if a.get("exists")
        ]
    }

    manifest_hash = hashlib.sha256(
        json.dumps(manifest_core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    manifest = {
        "schema": {
            "name": "FMIAF-snapshot-manifest",
            "version": SCHEMA_VERSION
        },
        "record_type": "snapshot_manifest",
        "created_utc": now_utc(),
        "snapshot_id": snapshot_id,
        "snapshot_hash": manifest_hash,
        "notes": args.notes,
        "summary": summary,
        "root_path_at_snapshot": master.get("root_path_at_scan"),
        "artifacts": artifacts,
        "missing_artifacts": missing,
        "source": {
            "master": str(master_path),
            "union": str(union_path),
            "union_run_id": union.get("union_run_id"),
        },
        "policy": {
            "immutable_manifest": True,
            "does_not_modify_dataset": True,
            "reproducibility_goal": "record exact artifact hashes and row counts for dataset state"
        },
        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION
        }
    }

    write_json(args.output, manifest)

    print("Snapshot manifest complete.")
    print(f"Snapshot ID:      {snapshot_id}")
    print(f"Snapshot hash:    {manifest_hash}")
    print(f"Artifacts:        {len(artifacts)}")
    print(f"Missing:          {len(missing)}")
    print(f"Files in master:  {summary['files_in_master']}")
    print(f"Files in union:   {summary['files_in_union']}")
    if "training_export_rows" in summary:
        print(f"Training rows:    {summary['training_export_rows']}")
    if "url_index_rows" in summary:
        print(f"URL rows:         {summary['url_index_rows']}")
    if "text_index_rows" in summary:
        print(f"Text rows:        {summary['text_index_rows']}")
    print(f"Manifest:         {args.output}")


if __name__ == "__main__":
    main()
