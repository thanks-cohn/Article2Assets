article_to_assets (ATA)

A modular document decompiler and structural asset pipeline

ATA (pronounced Ada) converts PDFs, scans, and visual documents into structured, machine-readable assets.

1. What ATA Produces

ATA transforms documents into:

Editable SVG layouts
Panel / region objects
Spatial OCR text-line objects
Canonical ML-ready JSONL datasets
Clickable compiled PDFs
Structured assets for retrieval, training, and analysis
2. Why ATA Exists

Most document tools stop at extraction.

ATA goes further — it deconstructs documents into reusable structural components.

Instead of treating PDFs as static files, ATA turns them into spatial datasets you can:

Analyze
Remix
Train on
Index
Rebuild

Use cases include:

Document AI research
Vision-language model training
Retrieval and embedding systems
Dataset curation
Layout analysis
Interactive editing pipelines
3. Core Features
3.1 Editable SVG Export

Convert documents into spatially accurate SVGs with movable text and layout elements.

3.2 Panel / Region Segmentation

Detect layout blocks, panels, and structural regions.

3.3 Spatial OCR Extraction

Extract text line-by-line with bounding boxes and preserved coordinates.

3.4 Canonical Dataset Export

Export structured JSONL suitable for:

COCO Layout
Hugging Face datasets
Retrieval pipelines
Custom schemas
3.5 Clickable PDF Compilation

Merge directory trees into linked, navigable PDFs.

3.6 Modular Pipeline Architecture

Each stage is independent, replaceable, and extensible.

4. Installation
pip install -r requirements.txt
Requirements
Python 3.14+
Tesseract OCR installed system-wide
Tkinter (for GUI)
5. Quick Start
5.1 GUI
python filemonster_gui.py
5.2 Pipeline Example
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
6. Philosophy

ATA is not just a PDF tool.

It is a document decompiler.

The goal is to convert visual documents into a canonical structure that can later be:

Reconstructed
Transformed
Indexed
Trained on
7. Development

ATA is in active development.

Contributions are welcome, especially in:

Segmentation
OCR improvements
Export formats
Reconstruction pipelines
GUI usability
Performance and scaling

Open an issue or pull request if you want to build on it.

8. Status

Active Development

The architecture is evolving as new modules and formats are introduced.

9. License

GNU Affero General Public License v3.0 (AGPL-3.0)

Free to use, modify, and distribute under AGPL
Network-deployed modifications must remain open-source
Commercial licensing available separately
