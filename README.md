article_to_assets (ATA)

A modular document decompiler and structural asset pipeline

ATA (pronounced Ada) converts PDFs, scans, and visual documents into structured, machine-readable assets.

What ATA Produces
Editable SVG layouts
Panel / region objects
Spatial OCR text-line objects
Canonical ML-ready JSONL datasets
Clickable compiled PDFs
Structured assets for retrieval, training, and analysis
Why ATA Exists

Most document tools stop at extraction.

ATA goes further—it deconstructs documents into reusable structural components.

Instead of treating PDFs as static files, ATA turns them into spatial datasets you can:

analyze
remix
train on
index
rebuild

Use cases include:

Document AI research
Vision-language model training
Retrieval and embedding systems
Dataset curation
Layout analysis
Interactive editing
Core Features
Editable SVG Export

Convert documents into spatially accurate SVGs with movable text and layout elements.

Panel / Region Segmentation

Detect layout blocks, panels, and structural regions.

Spatial OCR Extraction

Extract text line-by-line with bounding boxes and coordinates.

Canonical Dataset Export

Export structured JSONL suitable for:

COCO Layout
Hugging Face datasets
Retrieval pipelines
Custom schemas
Clickable PDF Compilation

Merge directories into linked, navigable PDFs.

Modular Pipeline

Each stage is independent and replaceable.

Installation
pip install -r requirements.txt
Requirements
Python 3.14+
Tesseract OCR installed system-wide
Tkinter (for GUI)
Quick Start
GUI
python filemonster_gui.py
Pipeline Example
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
Philosophy

ATA is not just a PDF tool.

It is a document decompiler.

The goal is to convert visual documents into a canonical structure that can later be:

reconstructed
transformed
indexed
trained on
Development

ATA is in active development.

Contributions are welcome, especially in:

segmentation
OCR improvements
export formats
reconstruction
GUI usability
performance

Open an issue or pull request if you want to build on it.

Status

Active development. Expect changes as the architecture evolves.

License

GNU Affero General Public License v3.0 (AGPL-3.0)

Free to use and modify under AGPL
Network-deployed modifications must remain open
Commercial licensing available separately
