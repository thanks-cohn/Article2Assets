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
# Clone Article2Assets
git clone https://github.com/thanks-cohn/Article2Assets.git

# Enter repository
cd Article2Assets

# Create virtual environment
python -m venv .venv

# Activate environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set your PDF here
SRC="$HOME/Documents/article.pdf"

# Output directories
OUT="$HOME/Desktop/a2a_output"
SAFE_DIR="$HOME/Desktop/a2a_safe_inputs"

mkdir -p "$OUT" "$SAFE_DIR"

# Copy input into controlled workspace
cp "$SRC" "$SAFE_DIR/input.pdf"

# Run full Article2Assets pipeline
./filemonster_scan "$SAFE_DIR/input.pdf" \
  -o "$OUT/master.json"

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

# Final output
echo
echo "DONE:"
echo "$OUT/final_svg"
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


##  REQUIREMENTS + REAL-WORLD NOTES


Python:
- Python 3.12 recommended
- Supported range: Python >=3.11,<3.14

Tested environment:
- Linux x86_64
- modern multi-threaded CPU
- integrated GPU

Known caveats:
- ASCII-safe filenames currently recommended
- keep sanitized PDFs outside output directories
- lower render zoom values perform better for very tall PDFs

Stress test:
- CNN Politics PDF
- 1859 × 14976
- ~3MB
- editable SVG reconstruction successful

Pipeline timings:
- filemonster_scan: ~0.007s
- spatial_text_module: ~0.381s
- layout_regions_module: ~2.655s
- panel_text_svg_export: ~1.066s

Results:
- 11 regions detected
- preserved layout structure
- preserved text positioning
- editable SVG output
