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

# article2assets

**PDF articles → editable SVG assets, text objects, layout crops, and spatial JSON.**

`article2assets` is the article/document mode of the FileMonster-style pipeline.

It takes article PDFs and turns them into:

- editable SVG pages
- movable article-region image objects
- line-by-line text objects
- cropped layout assets
- structured JSON records
- page-level relationships between text and regions

This is not just OCR.

This is article decomposition.

------------------------------------------------------------
## WHAT IT IS FOR
------------------------------------------------------------

Use this for:

- news articles
- research articles
- saved web-to-PDF pages
- reports
- newsletters
- document screenshots exported as PDFs
- article archives
- structured document datasets

For comics or manga, use a comic/panel profile.

For articles, use:

```bash
--profile article
```

That is the key.

------------------------------------------------------------
## INSTALL + RUN: BINGO BONGO
------------------------------------------------------------

Start in Downloads:

```bash
cd ~/Downloads
```

Unzip:

```bash
unzip Article2Assets-main.zip
```

Enter the folder:

```bash
cd ~/Downloads/Article2Assets-main
```

Install requirements:

```bash
pip install -r requirements.txt
```

Run article2assets:

```bash
./filemonster_scan "/home/user/path/to/article.pdf" -o master.json && \
python fm_spatial_text_module.py --master master.json --granularity line --show-boxes && \
python fm_layout_regions_module.py --master master.json --profile article --pdf-zoom 2.5 --crop-panels --crop-panel-group --svg --embed-page-background && \
python fm_panel_text_svg_export.py --master master.json --output-dir editable_svg_article
```

Open the output:

```bash
xdg-open editable_svg_article
```

That is the flow:

```text
unzip
cd
install
run
open
```

Bingo bongo.

------------------------------------------------------------
## REAL TEST COMMAND
------------------------------------------------------------

This is the exact structure proven to work well on article PDFs:

```bash
cd ~/Downloads/Article2Asset-main

pip install -r requirements.txt

./filemonster_scan "/home/big-bro/Documents/articles/Iran US War News_ JD Vance Fears Pete Hegseth 'Misleading' Trump On Iran War_ Report.pdf" -o master.json && \
python fm_spatial_text_module.py --master master.json --granularity line --show-boxes && \
python fm_layout_regions_module.py --master master.json --profile article --pdf-zoom 2.5 --crop-panels --crop-panel-group --svg --embed-page-background && \
python fm_panel_text_svg_export.py --master master.json --output-dir editable_svg_article
```

Then:

```bash
xdg-open editable_svg_article
```

------------------------------------------------------------
## WHAT COMES OUT
------------------------------------------------------------

After running, you get:

```text
editable_svg_article/
  ├── article_name.pdf.p0001.svg
  └── article_name.pdf.p0001.json
```

You also get module outputs beside the source record:

```text
*.pdf.fm.modules/
  ├── spatial_text.<run_id>.json
  ├── spatial_text.<run_id>.p0001.line.svg
  ├── layout_regions.<run_id>.json
  ├── layout_regions.<run_id>.p0001.svg
  └── layout_regions.<run_id>.P1_R*.png
```

The important outputs:

- final SVG with article assets + text
- final JSON with text, panels/regions, and relationships
- cropped region PNGs
- spatial text JSON
- layout region JSON

------------------------------------------------------------
## WHY ARTICLE MODE MATTERS
------------------------------------------------------------

The command uses:

```bash
--profile article
```

This tells the layout module to look for article-style structure:

- blocks
- callouts
- columns
- paragraph regions
- document sections

Using comic mode on an article can work, but it may split paragraphs like panels.

Article mode is the clean one for PDFs like reports and news pages.

------------------------------------------------------------
## PIPELINE BREAKDOWN
------------------------------------------------------------

### 1. Scan

```bash
./filemonster_scan "article.pdf" -o master.json
```

Creates the master file index.

### 2. Extract line text

```bash
python fm_spatial_text_module.py --master master.json --granularity line --show-boxes
```

Extracts text line-by-line with coordinates.

### 3. Extract article regions

```bash
python fm_layout_regions_module.py --master master.json --profile article --pdf-zoom 2.5 --crop-panels --crop-panel-group --svg --embed-page-background
```

Detects article layout blocks and saves each as an asset.

### 4. Export final SVG

```bash
python fm_panel_text_svg_export.py --master master.json --output-dir editable_svg_article
```

Builds clean SVG files with layered article assets and text objects.

------------------------------------------------------------
## WHAT THE SVG CONTAINS
------------------------------------------------------------

Each output SVG includes:

- page background
- cropped article-region image objects
- text-line objects
- region metadata
- object IDs
- JSON-backed relationships

The SVG is not just a screenshot.

It is a layered, inspectable, editable document structure.

------------------------------------------------------------
## BEST DEFAULTS
------------------------------------------------------------

For most article PDFs:

```bash
--profile article
--pdf-zoom 2.5
--crop-panels
--crop-panel-group
--svg
--embed-page-background
```

If the page is huge or slow:

```bash
--pdf-zoom 2.0
```

If tiny text or small layout blocks matter:

```bash
--pdf-zoom 3.0
```

------------------------------------------------------------
## COMMON PATH EXAMPLES
------------------------------------------------------------

Single article PDF:

```bash
./filemonster_scan "/home/user/Documents/articles/article.pdf" -o master.json
```

Folder of articles:

```bash
./filemonster_scan "/home/user/Documents/articles" -o master.json
```

Then run the same modules.

------------------------------------------------------------
## PHILOSOPHY
------------------------------------------------------------

An article is not just text.

It is:

- position
- hierarchy
- region
- flow
- layout
- visual emphasis

`article2assets` preserves that.

It turns a flat PDF into a structured asset system.

Text becomes objects.

Layout becomes objects.

The article becomes usable.
