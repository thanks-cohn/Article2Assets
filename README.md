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






