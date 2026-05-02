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

# article2assets

3 commands. 1 PDF. Full structure.

Turn article PDFs into:
- editable SVG layouts  
- movable region image objects  
- line-by-line text objects  
- cropped layout assets  
- structured JSON  

This is not OCR.
This is article decomposition.

## QUICK START

cd ~/Downloads
unzip Article2Assets-main.zip
cd Article2Assets-main
pip install -r requirements.txt
chmod +x filemonster_scan

./filemonster_scan "your_article.pdf" -o master.json && \
python fm_spatial_text_module.py --master master.json --granularity line --show-boxes && \
python fm_layout_regions_module.py --master master.json --profile article --pdf-zoom 2.5 --crop-panels --crop-panel-group --svg --embed-page-background && \
python fm_panel_text_svg_export.py --master master.json --output-dir editable_svg_article

xdg-open editable_svg_article
