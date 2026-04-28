# FileMonster

**Modular document decompiler and structural dataset pipeline**

Convert PDFs and image-based documents into editable, machine-readable structural assets for research, tooling, and downstream pipelines.

---

## Capabilities

FileMonster converts documents into:

- Editable SVG layouts  
- Panel / region objects  
- OCR text-line objects  
- Canonical ML-ready JSONL datasets  
- Clickable compiled PDFs  
- Structured assets for retrieval / training / research workflows  

---

## Why FileMonster Exists

Most document tooling stops at extraction.

FileMonster aims to **deconstruct documents into reusable structured components**, transforming static PDFs and scans into rich spatial datasets suitable for:

- Document AI research  
- Vision-language model training  
- Retrieval / embedding pipelines  
- Dataset curation  
- Layout analysis  
- Manual editing / document remixing  

---

## Core Features

### Editable SVG Export
Convert PDFs into spatially faithful SVGs with independently movable text and panel objects.

### Panel / Region Segmentation
Detect structural regions, layout blocks, and visual panels.

### Spatial OCR Extraction
Extract text line-by-line with bounding boxes and preserved spatial coordinates.

### Canonical Dataset Export
Produce rich JSONL records designed for later transformation into:

- COCO Layout  
- Hugging Face JSONL  
- Retrieval JSONL  
- Custom research schemas  

### Clickable PDF Compilation
Merge directory trees into linked / navigable compiled PDFs.

### Modular Pipeline Architecture
Each stage is independently replaceable, tunable, and extensible.

---

## Project Philosophy

FileMonster is being built as a **general document decompiler**, not merely a PDF utility.

Long-term goals include:

- Reconstructing documents from canonical JSON  
- Converting canonical data into multiple ML/dataset formats  
- Supporting comics, magazines, academic PDFs, scanned documents, and hybrid layouts  
- Enabling advanced structural document research  

---

## Installation

```bash
pip install -r requirements.txt
```

### System Requirements

- Python 3.14+
- Tesseract OCR installed system-wide
- Tkinter installed for GUI support

---

## Quick Start

### GUI

```bash
python filemonster_gui.py
```

---

### Manual Pipeline

```bash
./filemonster_scan input_folder -o master.json

./fm_spatial_text_module.py \
  --master master.json \
  --granularity line

./fm_layout_regions_module.py \
  --master master.json \
  --profile comic

./fm_panel_text_svg_export.py \
  --master master.json \
  --output-dir editable_svg

./fm_export_canonical_dataset.py \
  --input-dir editable_svg \
  --output-jsonl dataset.jsonl
```

---

## Development Notes

Contributions, experiments, and module additions are welcome.

If you improve:

- segmentation  
- export formats  
- reconstruction  
- GUI functionality  
- performance / scalability  

please open an Issue or Pull Request.

We are actively building FileMonster into a broader document decompilation framework and deeply appreciate anyone who takes interest in the project.

---

## Status

**Active Development**

The project is evolving rapidly and architectural changes may occur as new modules and formats are introduced.

---
## License

FileMonster is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

This means:

- You are free to use, modify, and distribute FileMonster under AGPL terms  
- Derivative works and network-deployed modified versions must also remain open under AGPL  
- Commercial / proprietary licensing is available separately for organizations seeking closed-source or private integration rights  

For commercial licensing inquiries, contact the project maintainer
