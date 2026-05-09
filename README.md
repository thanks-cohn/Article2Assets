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

# Go to where you downloaded the project

```text
cd ~/Downloads/Article2Assets-main
```

# Install everything needed (just once)
```text
pip install -r requirements.txt
```
# Make the scanner executable (important)

```text
chmod +x filemonster_scan
```
------------------------------------------------------------
 STEP 1 — SCAN YOUR FILE
------------------------------------------------------------
```text
./filemonster_scan "your_article.pdf" -o master.json
```
# ↑ Replace "your_article.pdf" with your file
    
  You can also pass a directory:

```text  
  ./filemonster_scan "/path/to/folder"
```


**This builds a master index of your files**

------------------------------------------------------------
 STEP 2 — EXTRACT TEXT (LINE BY LINE)
------------------------------------------------------------
```text
python fm_spatial_text_module.py --master master.json --granularity line --show-boxes
```

# This pulls every line of text + coordinates

------------------------------------------------------------
 STEP 3 — DETECT ARTICLE STRUCTURE
------------------------------------------------------------


```text
python fm_layout_regions_module.py --master master.json --profile article --pdf-zoom 2.5 --crop-panels --crop-panel-group --svg --embed-page-background
```


# --profile article is the key
# This finds paragraphs, columns, callouts, sections

------------------------------------------------------------
 STEP 4 — BUILD FINAL SVG + JSON
------------------------------------------------------------
```text
python fm_panel_text_svg_export.py --master master.json --output-dir editable_svg_article
```

# This combines everything into:
# SVG (visual layout) + JSON (structure)

------------------------------------------------------------
 STEP 5 — OPEN THE RESULT
------------------------------------------------------------
```text
xdg-open editable_svg_article
```


# Open the SVG file
# Move blocks around → you’ll immediately see what this is

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

cnn_iran_factcheck.pdf

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

cnn_iran_factcheck.pdf

### Long-Page PDF Stress Test

Tested successfully against a:

- 1-page
- 14976px tall
- ~3MB CNN article PDF

```
cd ~/Desktop/Article2Assets
source .venv/bin/activate

# Change this to the PDF you want to process.
SRC="$HOME/Documents/articles/example_article.pdf"

# Safe working paths.
SAFE_DIR="$HOME/Desktop/a2a_safe_inputs"
SAFE_NAME="article_input.pdf"
SAFEPDF="$SAFE_DIR/$SAFE_NAME"

OUT="$HOME/Desktop/Article2Assets/a2a_article_test"

rm -rf "$OUT"
mkdir -p "$OUT"
mkdir -p "$SAFE_DIR"

# Copy the PDF to a simple ASCII-safe filename.
# This avoids path issues with spaces, punctuation, apostrophes, and nested output folders.
cp "$SRC" "$SAFEPDF"

echo "== PDF INFO =="
python - <<'PY' "$SAFEPDF"
import fitz, os, sys
p = sys.argv[1]
doc = fitz.open(p)
print("file:", p)
print("pages:", len(doc))
print("size_mb:", round(os.path.getsize(p) / 1024 / 1024, 3))
for i, page in enumerate(doc):
    print(f"page_{i+1}_dims:", round(page.rect.width), "x", round(page.rect.height))
doc.close()
PY

echo
echo "== STAGE 1: SCAN =="
time ./filemonster_scan "$SAFEPDF" -o "$OUT/master.json"

echo
echo "== STAGE 2: SPATIAL TEXT =="
time python fm_spatial_text_module.py \
  --master "$OUT/master.json" \
  --granularity line \
  --show-boxes

echo
echo "== STAGE 3: LAYOUT REGIONS =="
time python fm_layout_regions_module.py \
  --master "$OUT/master.json" \
  --profile article \
  --pdf-zoom 1.0 \
  --crop-panels \
  --crop-panel-group \
  --svg \
  --embed-page-background

echo
echo "== STAGE 4: FINAL SVG EXPORT =="
time python fm_panel_text_svg_export.py \
  --master "$OUT/master.json" \
  --output-dir "$OUT/final_svg"

echo
echo "== FILE COUNTS =="
find "$OUT" -type f | awk '
/\.svg$/ {svg++}
/\.json$/ {json++}
/\.jsonl$/ {jsonl++}
/\.png$/ {png++}
END{
print "svg:", svg+0
print "json:", json+0
print "jsonl:", jsonl+0
print "png:", png+0
}'

echo
echo "== LARGEST SVG FILES =="
find "$OUT" -name "*.svg" -exec du -h {} \; | sort -hr | head -20

echo
echo "== OPEN RESULT =="
xdg-open "$OUT/final_svg" >/dev/null 2>&1 &
```





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
