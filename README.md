====================================================================
# DATA
Documents and Articles to Assets
====================================================================

Modular document decompiler and structural dataset pipeline.

Convert PDFs and image-based documents into editable, machine-readable
structural assets for research, tooling, and downstream pipelines.


--------------------------------------------------------------------
CAPABILITIES
--------------------------------------------------------------------

DATA converts documents into:

- Editable SVG layouts
- Panel / region objects
- OCR text-line objects
- Canonical ML-ready JSONL datasets
- Clickable compiled PDFs
- Structured assets for retrieval, training, and research workflows


--------------------------------------------------------------------
WHY DATA EXISTS
--------------------------------------------------------------------

Most document tooling stops at extraction.

DATA is designed to deconstruct documents and articles into reusable
structured components, transforming static PDFs and scans into rich
spatial datasets suitable for:

- Document AI research
- Vision-language model training
- Retrieval and embedding pipelines
- Dataset curation
- Layout analysis
- Manual editing and document remixing


--------------------------------------------------------------------
CORE FEATURES
--------------------------------------------------------------------

Editable SVG Export
Convert documents into spatially faithful SVGs with independently
movable text and panel objects.

Panel / Region Segmentation
Detect structural regions, layout blocks, and visual panels.

Spatial OCR Extraction
Extract text line-by-line with bounding boxes and preserved spatial
coordinates.

Canonical Dataset Export
Produce rich JSONL records designed for transformation into:

- COCO Layout
- Hugging Face JSONL
- Retrieval JSONL
- Custom research schemas

Clickable PDF Compilation
Merge directory trees into linked, navigable compiled PDFs.

Modular Pipeline Architecture
Each stage is independently replaceable, tunable, and extensible.


--------------------------------------------------------------------
PROJECT PHILOSOPHY
--------------------------------------------------------------------

DATA is being built as a general document and article decompiler,
not merely a PDF utility.

Long-term goals include:

- Reconstructing documents from canonical JSON
- Converting canonical data into multiple ML and dataset formats
- Supporting comics, magazines, academic PDFs, scanned documents,
  and hybrid layouts
- Enabling advanced structural document research


--------------------------------------------------------------------
INSTALLATION
--------------------------------------------------------------------

pip install -r requirements.txt


SYSTEM REQUIREMENTS

- Python 3.14+
- Tesseract OCR installed system-wide
- Tkinter installed for GUI support


--------------------------------------------------------------------
QUICK START
--------------------------------------------------------------------

GUI

python filemonster_gui.py


MANUAL PIPELINE

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


--------------------------------------------------------------------
DEVELOPMENT NOTES
--------------------------------------------------------------------

Contributions, experiments, and module additions are welcome.

If you improve:

- Segmentation
- Export formats
- Reconstruction
- GUI functionality
- Performance and scalability

please open an Issue or Pull Request.

DATA is being actively developed into a broader document
decompilation framework.


--------------------------------------------------------------------
STATUS
--------------------------------------------------------------------

Active Development

The project is evolving rapidly and architectural changes may occur
as new modules and formats are introduced.


--------------------------------------------------------------------
LICENSE
--------------------------------------------------------------------

DATA is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

- You are free to use, modify, and distribute DATA under AGPL terms
- Derivative works and network-deployed versions must remain open
  under AGPL
- Commercial and proprietary licensing is available separately

For commercial licensing inquiries, please contact the maintainer.
