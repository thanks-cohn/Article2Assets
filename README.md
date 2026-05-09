```
  █████╗ ██████╗ ████████╗██╗ ██████╗██╗     ███████╗
 ██╔══██╗██╔══██╗╚══██╔══╝██║██╔════╝██║     ██╔════╝
 ███████║██████╔╝   ██║   ██║██║     ██║     █████╗
 ██╔══██║██╔══██╗   ██║   ██║██║     ██║     ██╔══╝
 ██║  ██║██║  ██║   ██║   ██║╚██████╗███████╗███████╗
 ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝╚══════╝╚══════╝

       ██████╗     █████╗ ███████╗███████╗███████╗████████╗███████╗
       ╚════██╗   ██╔══██╗██╔════╝██╔════╝██╔════╝╚══██╔══╝██╔════╝
        █████╔╝   ███████║███████╗███████╗█████╗     ██║   ███████╗
       ██╔═══╝    ██╔══██║╚════██║╚════██║██╔══╝     ██║   ╚════██║
       ███████╗   ██║  ██║███████║███████║███████╗   ██║   ███████║
       ╚══════╝   ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝   ╚═╝   ╚══════╝
```

```
============================================================
 ARTICLE2ASSETS
 Turn articles into assets. Instantly.
============================================================
```
Ever wanted to...

Turn a PDF article into editable blocks?
Break a document into movable images?
Extract structured text + layout for ML or search?

This does exactly that.

------------------------------------------------------------
 WHAT THIS ACTUALLY IS
------------------------------------------------------------

Not OCR.

This is:

  PDF → structure → regions → text → assets → SVG → JSON

Every paragraph becomes an object.
Every line becomes usable.

------------------------------------------------------------
 RUN IT (STEP BY STEP)
------------------------------------------------------------

## QUICK START


1. Put your PDF somewhere easy to access.

Example:

  ~/Documents/article.pdf

2. Run this:

------------------------------------------------------------
```text
cd ~/Desktop/Article2Assets
source .venv/bin/activate

SRC="$HOME/Documents/article.pdf"

OUT="$HOME/Desktop/a2a_output"
SAFE_DIR="$HOME/Desktop/a2a_safe_inputs"

mkdir -p "$OUT"
mkdir -p "$SAFE_DIR"

cp "$SRC" "$SAFE_DIR/input.pdf"

./filemonster_scan "$SAFE_DIR/input.pdf" -o "$OUT/master.json"

python fm_spatial_text_module.py \
  --master "$OUT/master.json" \
  --granularity line \
  --show-boxes

python fm_layout_regions_module.py \
  --master "$OUT/master.json" \
  --profile article \
  --pdf-zoom 1.0 \
  --crop-panels \
  --crop-panel-group \
  --svg \
  --embed-page-background

python fm_panel_text_svg_export.py \
  --master "$OUT/master.json" \
  --output-dir "$OUT/final_svg"

xdg-open "$OUT/final_svg"
```
------------------------------------------------------------

3. Open the SVG.

Move blocks around.

You’ll immediately understand what Article2Assets does.

------------------------------------------------------------
 WHAT YOU GET
------------------------------------------------------------
```
editable_svg_article/
  ├── page_0001.svg
  └── page_0001.json
```
------------------------------------------------------------
 WHAT YOU CAN DO NOW
------------------------------------------------------------

- move article blocks like design elements
- extract structured datasets
- build search/index systems
- feed layout-aware ML models
- reconstruct documents visually

------------------------------------------------------------
 CORE IDEA
------------------------------------------------------------

An article is not just text.

It is:

- layout
- hierarchy
- flow
- emphasis

article2assets preserves all of it.

------------------------------------------------------------
 FINAL
------------------------------------------------------------

Run it once.
Open the SVG.
Move a paragraph.

You’ll understand immediately.
============================================================


## Python Requirement

- Python 3.12.x recommended
- Supported range: Python >=3.11,<3.14
- Python 3.14+ may fail due to scientific stack wheel availability during newer ecosystem transitions.

## Notes From Real-World Testing

### Python Runtime

Article2Assets currently targets:

- Python 3.12.x recommended
- Supported range: Python >=3.11,<3.14

Python 3.14+ may fail during dependency installation due to
scientific stack wheel availability lag (NumPy/OpenCV ecosystem).

Confirmed working environment:

- Python 3.12.8
- NumPy 2.4.4
- OpenCV 4.13.0
- Pillow 12.2.0
- PyMuPDF 1.27.2.3
- pytesseract 0.3.13

### SVG / Path Notes

During real-world testing with extremely long-form article PDFs
(CNN/Independent exported webpage PDFs), SVG export worked correctly
after sanitizing filenames and avoiding nested relative scan paths.

Observed issue:

- placing the sanitized PDF inside the output directory caused
  duplicated relative paths during module reconstruction

Example failure pattern:

output_dir/output_dir/file.pdf

Resolution:

- keep sanitized source PDFs outside output directories
- prefer simple ASCII-safe filenames for current SVG crop linking

Example:

Is_the_draft_back.pdf

### Long-Page PDF Stress Test

Tested successfully against a:

- 1-page
- 14976px tall
- ~3MB CNN article PDF

Pipeline stages:

- file scan
- spatial text extraction
- layout region extraction
- crop generation
- SVG reconstruction
- panel/text overlay export

The generated SVG reconstruction successfully preserved:

- text positioning
- panel regions
- crop overlays
- editable spatial structure

### Performance Observations

Approximate timings on Garuda Linux / i7-1255U:

- file scan: ~0.005s
- spatial text extraction: ~0.35s

Layout extraction speed depends heavily on:

- page height
- render zoom
- OpenCV contour complexity

Very tall webpage-style PDFs benefit from lower render zoom values
(e.g. --pdf-zoom 1.0).


Pipeline stages:

- file scan
- spatial text extraction
- layout region extraction
- crop generation
- SVG reconstruction
- panel/text overlay export

The generated SVG reconstruction successfully preserved:

- text positioning
- panel regions
- crop overlays
- editable spatial structure

### Performance Observations

Approximate timings on Garuda Linux / i7-1255U:

- file scan: ~0.005s
- spatial text extraction: ~0.35s

Layout extraction speed depends heavily on:

- page height
- render zoom
- OpenCV contour complexity

Very tall webpage-style PDFs benefit from lower render zoom values
(e.g. --pdf-zoom 1.0).

### Benchmark: Real-World Long-Form News Article PDF

Environment:

- Linux x86_64
- modern multi-threaded CPU
- integrated GPU
- Python 3.12

Stress-test document:

- CNN Politics article PDF
- 1 page
- ~3 MB
- dimensions: 1859 × 14976

Pipeline timings:

| Stage | Time |
|---|---|
| filemonster_scan | ~0.007s |
| spatial_text_module | ~0.381s |
| layout_regions_module | ~2.655s |
| panel_text_svg_export | ~1.066s |

Extraction results:

- regions detected: 11
- blocks detected: 11
- crops generated: 11
- SVGs generated: 1
- JSON outputs: 2

Generated editable SVG:

- size: ~5 MB
- fully editable
- preserved panel overlays
- preserved text positioning
- preserved spatial structure

Notes:

- long webpage-style PDFs work successfully
- lower zoom values (e.g. --pdf-zoom 1.0) perform better for extremely tall documents
- sanitized ASCII-safe filenames improve SVG crop portability across viewers/editors
