#!/usr/bin/env python3
"""
run.py
Usage: python run.py path/to/file.html

Outputs into ./output/
 - output/base.pdf        (rendered HTML -> PDF by Playwright)
 - output/overlay.pdf     (PDF overlay with AcroForm fields)
 - output/final_fill.pdf  (base + overlay merged => fillable PDF)
 - output/fields.json     (extracted field list)
"""

import sys, os, asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from pdfrw import PdfReader, PdfWriter, PageMerge

# Constants: A4 in PDF points
A4_WIDTH_PT, A4_HEIGHT_PT = A4  # (~595.27, 841.89)
CSS_PX_TO_PT = 72.0 / 96.0     # CSS px -> PDF points (0.75)

html_path : str = 'D:\MyFolder\Sources\huynhtrungducgrowth\gitlab\"Convert HTML To PDF"\access\file_example\"Enterprise Agreement".html'
out_pdf : str = 'D:\MyFolder\Sources\huynhtrungducgrowth\gitlab\"Convert HTML To PDF"\access\result_pdf'

async def render_html_to_pdf(html_path: str, out_pdf: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 1700})
        # load local file
        await page.goto(f"file://{Path(html_path).resolve()}", wait_until="networkidle")
        await page.pdf(path=out_pdf, format="A4", print_background=True)
        # Extract bounding boxes of inputs/selects/textareas
        fields = await page.evaluate("""
        () => {
            const nodes = Array.from(document.querySelectorAll('input, select, textarea'));
            return nodes.map((el, idx) => {
                const r = el.getBoundingClientRect();
                const tag = el.tagName.toLowerCase();
                const type = el.type || '';
                const name = el.name || el.id || el.placeholder || (tag + '_' + idx);
                const options = (tag === 'select') ? Array.from(el.options).map(o => ({value:o.value, text:o.text})) : null;
                return {
                    tag, type, name,
                    x: r.x, y: r.y, width: r.width, height: r.height,
                    options
                };
            });
        }
        """)
        await browser.close()
        return fields


def make_overlay_pdf(overlay_path: str, fields: list):
    """
    Create a PDF the same size as A4 with AcroForm fields at positions from `fields`.
    ReportLab's origin is bottom-left.
    fields use CSS px (page.evaluate), convert to points and invert Y.
    """
    c = canvas.Canvas(overlay_path, pagesize=A4)
    form = c.acroform

    for f in fields:
        # convert CSS px -> PDF points
        x_pt = f['x'] * CSS_PX_TO_PT
        y_pt_css = f['y']
        h_pt = f['height'] * CSS_PX_TO_PT
        w_pt = f['width'] * CSS_PX_TO_PT
        # convert y: css y 0 at top -> pdf y 0 at bottom
        y_pt = A4_HEIGHT_PT - (y_pt_css * CSS_PX_TO_PT) - h_pt

        name = str(f['name'])
        tag = f['tag']
        typ = f.get('type', '')

        # sanitize sizes: minimums to avoid zero boxes
        if w_pt < 20: w_pt = max(w_pt, 40)
        if h_pt < 10: h_pt = max(h_pt, 14)

        # Map element types to form widgets
        if tag == 'input' and typ in ('checkbox',):
            # checkbox (ReportLab supports checkbox)
            form.checkbox(name=name, x=x_pt, y=y_pt, size=min(w_pt, h_pt), checked=False)
        else:
            # Use text field for text/textarea/select/number/date/email by default
            # Reportlab textfield params: name, x,y,width,height
            # Using borderStyle='underlined' for inline look
            try:
                form.textfield(name=name, tooltip=name,
                               x=x_pt, y=y_pt, width=w_pt, height=h_pt,
                               borderStyle='underlined', forceBorder=True)
            except Exception as e:
                # fallback: draw rect and then textfield
                c.rect(x_pt, y_pt, w_pt, h_pt, stroke=1, fill=0)
                form.textfield(name=name, tooltip=name, x=x_pt, y=y_pt, width=w_pt, height=h_pt)

    c.showPage()
    c.save()


def merge_pdfs(base_pdf_path: str, overlay_pdf_path: str, final_out_path: str):
    base = PdfReader(base_pdf_path)
    overlay = PdfReader(overlay_pdf_path)
    for i, page in enumerate(base.pages):
        # defensively handle overlay page count
        overlay_page = overlay.pages[min(i, len(overlay.pages)-1)]
        merger = PageMerge(page)
        merger.add(overlay_page).render()
    PdfWriter().write(final_out_path, base)


# async def run(html_path: str, out_dir: str):
async def run():
    os.makedirs(out_dir, exist_ok=True)
    base_pdf = os.path.join(out_dir, "base_render.pdf")
    overlay_pdf = os.path.join(out_dir, "overlay.pdf")
    final_pdf = os.path.join(out_dir, "final_fill.pdf")
    fields_json = os.path.join(out_dir, "fields.json")

    print("Rendering HTML to PDF with Playwright...")
    fields = await render_html_to_pdf(html_path, base_pdf)
    print(f"Found {len(fields)} fields. Writing {fields_json} ...")
    with open(fields_json, "w", encoding="utf-8") as fh:
        json.dump(fields, fh, indent=2, ensure_ascii=False)

    print("Creating overlay PDF with AcroForm fields (ReportLab)...")
    make_overlay_pdf(overlay_pdf, fields)

    print("Merging overlay onto base PDF...")
    merge_pdfs(base_pdf, overlay_pdf, final_pdf)

    print("\nDone. Files created in:", out_dir)
    print(" -", base_pdf)
    print(" -", overlay_pdf)
    print(" -", final_pdf)
    print(" -", fields_json)
    print("\nOpen final_fill.pdf in Adobe Reader or browser to test filling fields.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run.py path/to/file.html")
        sys.exit(1)
    # html_file = sys.argv[1]
    # out = "output"
    # asyncio.run(run(html_file, out))
    asyncio.run(run())
