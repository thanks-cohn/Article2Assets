#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone


SCHEMA_VERSION = "0.2.0"
TOOL_NAME = "fm_audit_report"
TOOL_VERSION = "0.2.0"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    rows = []
    path = Path(path)

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


def write_json(path, data):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def safe_read_json(path):
    try:
        return read_json(path), None
    except Exception as e:
        return None, str(e)


def grade_dataset(critical, warnings):
    if critical:
        return "BROKEN", False
    if warnings >= 6:
        return "C", True
    if warnings >= 3:
        return "B", True
    if warnings >= 1:
        return "A-", True
    return "A", True


def pct(num, den):
    if not den:
        return 0.0
    return round((num / den) * 100, 2)


def main():
    parser = argparse.ArgumentParser(
        description="FileMonster audit report: research-readiness dashboard."
    )

    parser.add_argument("--master", required=True, help="FileMonster master JSON")
    parser.add_argument("--module-index", default=None, help="Defaults beside master as filemonster_module_index.jsonl")
    parser.add_argument("--validation-report", default=None, help="Optional filemonster_validation_report.json")
    parser.add_argument("--union", default=None, help="Optional filemonster_layer_union.json")
    parser.add_argument("--output-json", default=None, help="Optional machine-readable audit JSON")
    parser.add_argument("--output-md", default=None, help="Optional human-readable Markdown report")

    args = parser.parse_args()

    master_path = Path(args.master).expanduser().resolve()
    master = read_json(master_path)
    root = Path(master["root_path_at_scan"]).expanduser().resolve()

    module_index_path = (
        Path(args.module_index).expanduser().resolve()
        if args.module_index
        else master_path.parent / "filemonster_module_index.jsonl"
    )

    module_entries = read_jsonl(module_index_path)

    validation = None
    if args.validation_report:
        validation_path = Path(args.validation_report).expanduser().resolve()
        if validation_path.exists():
            validation = read_json(validation_path)

    union = None
    if args.union:
        union_path = Path(args.union).expanduser().resolve()
        if union_path.exists():
            union = read_json(union_path)

    files = master.get("files", [])

    media_counter = Counter()
    format_counter = Counter()
    module_counter = Counter()
    run_counter = Counter()
    module_version_counter = Counter()

    file_missing = []
    sidecar_missing = []
    module_missing = []
    bad_index_lines = 0

    entries_by_fm = defaultdict(list)

    for f in files:
        media_counter[f.get("media_type", "unknown")] += 1
        format_counter[f.get("format", "unknown")] += 1

        rel_file = f.get("path")
        rel_sidecar = f.get("sidecar")

        if rel_file and not (root / rel_file).exists():
            file_missing.append(rel_file)

        if rel_sidecar and not (root / rel_sidecar).exists():
            sidecar_missing.append(rel_sidecar)

    total_module_urls = 0
    total_module_blocks = 0
    total_module_text_chars = 0
    legacy_no_run_id_layers = 0
    missing_source_sha_layers = 0

    for entry in module_entries:
        if "_bad_json_line" in entry:
            bad_index_lines += 1
            continue

        fm_id = entry.get("fm_id")
        module_name = entry.get("module_name", "unknown")
        run_id = entry.get("run_id") or "no_run_id"
        rel_module = entry.get("module_json")

        module_counter[module_name] += 1
        run_counter[run_id] += 1

        if run_id == "no_run_id":
            legacy_no_run_id_layers += 1

        if not entry.get("source_sha256"):
            missing_source_sha_layers += 1

        if fm_id:
            entries_by_fm[fm_id].append(entry)

        if not rel_module:
            module_missing.append({
                "reason": "index_entry_missing_module_json",
                "entry": entry
            })
            continue

        module_path = root / rel_module
        if not module_path.exists():
            module_missing.append({
                "reason": "module_json_file_missing",
                "module_json": rel_module
            })
            continue

        mod, err = safe_read_json(module_path)
        if err:
            module_missing.append({
                "reason": "module_json_unreadable",
                "module_json": rel_module,
                "error": err
            })
            continue

        module_version = mod.get("module", {}).get("version", "unknown")
        module_version_counter[f"{module_name}:{module_version}"] += 1

        data = mod.get("data", {}) if isinstance(mod, dict) else {}

        urls = data.get("urls")
        if isinstance(urls, list):
            total_module_urls += len(urls)

        blocks = data.get("blocks")
        if isinstance(blocks, list):
            total_module_blocks += len(blocks)

        text = data.get("text")
        if isinstance(text, dict):
            total_module_text_chars += len(text.get("plain") or "")

    files_with_modules = len(entries_by_fm)
    files_without_modules = [
        f.get("path")
        for f in files
        if f.get("fm_id") not in entries_by_fm
    ]

    union_summary = union.get("summary", {}) if union else {}
    validation_summary = validation.get("summary", {}) if validation else {}

    active_files = union.get("files", []) if union else []
    active_text_chars = 0
    active_url_count = 0
    active_block_count = 0
    files_with_no_text = []
    files_with_no_urls = []
    files_with_no_blocks = []

    for uf in active_files:
        active = uf.get("active_view", {})
        text = active.get("text", {})
        plain = text.get("plain", "") if isinstance(text, dict) else ""
        urls = active.get("urls", [])
        blocks = active.get("blocks", [])

        text_len = len(plain)
        url_len = len(urls) if isinstance(urls, list) else 0
        block_len = len(blocks) if isinstance(blocks, list) else 0

        active_text_chars += text_len
        active_url_count += url_len
        active_block_count += block_len

        if text_len == 0:
            files_with_no_text.append(uf.get("file"))

        if url_len == 0:
            files_with_no_urls.append(uf.get("file"))

        if block_len == 0:
            files_with_no_blocks.append(uf.get("file"))

    duplicate_layers = union_summary.get("layers_duplicate", 0)
    stale_layers = union_summary.get("layers_stale", 0)
    pending_layers = union_summary.get("layers_pending_review", 0)
    union_conflicts = union_summary.get("conflicts", 0)
    union_warnings = union_summary.get("warnings", 0)
    files_without_layers = union_summary.get("files_without_layers", 0)

    critical = []
    warnings = []

    if file_missing:
        critical.append(f"{len(file_missing)} source files are missing")

    if sidecar_missing:
        warnings.append(f"{len(sidecar_missing)} sidecars are missing")

    if bad_index_lines:
        critical.append(f"{bad_index_lines} bad JSONL lines in module index")

    if module_missing:
        critical.append(f"{len(module_missing)} module JSON files are missing or unreadable")

    if validation and validation_summary.get("invalid", 0):
        critical.append(f"{validation_summary.get('invalid')} invalid module blocks")

    if union_conflicts:
        critical.append(f"{union_conflicts} union conflicts")

    if stale_layers:
        critical.append(f"{stale_layers} stale layers detected")

    if files_without_modules:
        warnings.append(f"{len(files_without_modules)} files have no module entries")

    if files_without_layers:
        warnings.append(f"{files_without_layers} files have no union layers")

    if legacy_no_run_id_layers:
        warnings.append(f"{legacy_no_run_id_layers} legacy no_run_id layers")

    if missing_source_sha_layers:
        warnings.append(f"{missing_source_sha_layers} layers missing source_sha256")

    if pending_layers:
        warnings.append(f"{pending_layers} layers pending review")

    if files_with_no_text:
        warnings.append(f"{len(files_with_no_text)} files have no active text")

    grade, ready = grade_dataset(critical, len(warnings))

    audit = {
        "schema": {"name": "FMIAF-audit-report", "version": SCHEMA_VERSION},
        "record_type": "audit_report",
        "created_utc": now_utc(),
        "master": str(master_path),
        "root": str(root),
        "module_index": str(module_index_path),
        "research_readiness": {
            "research_ready": ready,
            "readiness_grade": grade,
            "critical_count": len(critical),
            "warning_count": len(warnings),
            "critical": critical,
            "warnings": warnings
        },
        "summary": {
            "files_total": len(files),
            "files_missing": len(file_missing),
            "sidecars_missing": len(sidecar_missing),
            "module_index_entries": len(module_entries),
            "bad_module_index_lines": bad_index_lines,
            "module_files_missing_or_unreadable": len(module_missing),
            "files_with_modules": files_with_modules,
            "files_without_modules": len(files_without_modules),
            "total_module_urls": total_module_urls,
            "total_module_ocr_blocks": total_module_blocks,
            "total_module_text_chars": total_module_text_chars,
            "active_url_count": active_url_count,
            "active_ocr_blocks": active_block_count,
            "active_text_chars": active_text_chars,
            "files_with_no_text": len(files_with_no_text),
            "files_with_no_urls": len(files_with_no_urls),
            "files_with_no_blocks": len(files_with_no_blocks),
            "legacy_no_run_id_layers": legacy_no_run_id_layers,
            "missing_source_sha_layers": missing_source_sha_layers,
            "duplicate_layers": duplicate_layers,
            "stale_layers": stale_layers,
            "pending_review_layers": pending_layers,
            "union_warnings": union_warnings,
            "union_conflicts": union_conflicts,
            "ocr_text_coverage_percent": pct(len(files) - len(files_with_no_text), len(files)),
            "url_coverage_percent": pct(len(files) - len(files_with_no_urls), len(files)),
            "module_coverage_percent": pct(files_with_modules, len(files))
        },
        "media": dict(media_counter),
        "formats": dict(format_counter),
        "modules": dict(module_counter),
        "module_versions": dict(module_version_counter),
        "runs": dict(run_counter),
        "validation_summary": validation_summary,
        "union_summary": union_summary,
        "problems": {
            "files_missing": file_missing[:100],
            "sidecars_missing": sidecar_missing[:100],
            "module_missing_or_unreadable": module_missing[:100],
            "files_without_modules": files_without_modules[:100],
            "files_with_no_text": files_with_no_text[:100],
            "files_with_no_urls": files_with_no_urls[:100],
            "files_with_no_blocks": files_with_no_blocks[:100]
        },
        "provenance": {
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION
        }
    }

    print()
    print("FileMonster Audit Report")
    print("========================")
    print(f"Research ready:          {str(ready).lower()}")
    print(f"Readiness grade:         {grade}")
    print(f"Critical issues:         {len(critical)}")
    print(f"Warnings:                {len(warnings)}")
    print()
    print(f"Files total:             {audit['summary']['files_total']}")
    print(f"Files missing:           {audit['summary']['files_missing']}")
    print(f"Sidecars missing:        {audit['summary']['sidecars_missing']}")
    print(f"Module index entries:    {audit['summary']['module_index_entries']}")
    print(f"Module files broken:     {audit['summary']['module_files_missing_or_unreadable']}")
    print(f"Files with modules:      {audit['summary']['files_with_modules']}")
    print(f"Files without modules:   {audit['summary']['files_without_modules']}")
    print()
    print(f"Active text chars:       {audit['summary']['active_text_chars']}")
    print(f"Active URLs:             {audit['summary']['active_url_count']}")
    print(f"Active OCR blocks:       {audit['summary']['active_ocr_blocks']}")
    print(f"Text coverage:           {audit['summary']['ocr_text_coverage_percent']}%")
    print(f"URL coverage:            {audit['summary']['url_coverage_percent']}%")
    print(f"Module coverage:         {audit['summary']['module_coverage_percent']}%")
    print()
    print(f"Legacy no_run_id layers: {legacy_no_run_id_layers}")
    print(f"Missing source SHA:      {missing_source_sha_layers}")
    print(f"Duplicate layers:        {duplicate_layers}")
    print(f"Stale layers:            {stale_layers}")
    print(f"Pending review layers:   {pending_layers}")
    print(f"Union conflicts:         {union_conflicts}")
    print(f"Union warnings:          {union_warnings}")
    print()
    print("Modules:")
    for name, count in sorted(module_counter.items()):
        print(f"  {name}: {count}")
    print()
    print("Runs:")
    for run_id, count in sorted(run_counter.items()):
        print(f"  {run_id}: {count}")

    if critical:
        print()
        print("Critical:")
        for item in critical:
            print(f"  - {item}")

    if warnings:
        print()
        print("Warnings:")
        for item in warnings:
            print(f"  - {item}")

    if args.output_json:
        write_json(args.output_json, audit)
        print(f"\nAudit JSON saved: {args.output_json}")

    if args.output_md:
        md = []
        md.append("# FileMonster Audit Report")
        md.append("")
        md.append(f"- Created UTC: `{audit['created_utc']}`")
        md.append(f"- Research ready: **{str(ready).lower()}**")
        md.append(f"- Readiness grade: **{grade}**")
        md.append(f"- Master: `{audit['master']}`")
        md.append(f"- Root: `{audit['root']}`")
        md.append("")
        md.append("## Readiness")
        md.append(f"- Critical issues: **{len(critical)}**")
        md.append(f"- Warnings: **{len(warnings)}**")
        if critical:
            md.append("")
            md.append("### Critical")
            for item in critical:
                md.append(f"- {item}")
        if warnings:
            md.append("")
            md.append("### Warnings")
            for item in warnings:
                md.append(f"- {item}")
        md.append("")
        md.append("## Summary")
        for k, v in audit["summary"].items():
            md.append(f"- **{k}**: {v}")
        md.append("")
        md.append("## Modules")
        for name, count in sorted(module_counter.items()):
            md.append(f"- `{name}`: {count}")
        md.append("")
        md.append("## Runs")
        for run_id, count in sorted(run_counter.items()):
            md.append(f"- `{run_id}`: {count}")
        md.append("")
        md.append("## Module Versions")
        for name, count in sorted(module_version_counter.items()):
            md.append(f"- `{name}`: {count}")

        Path(args.output_md).expanduser().resolve().write_text(
            "\n".join(md),
            encoding="utf-8"
        )
        print(f"Audit Markdown saved: {args.output_md}")


if __name__ == "__main__":
    main()
