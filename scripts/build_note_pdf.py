"""
Builds docs/solution_note.pdf from docs/solution_note.md (A4, two pages).
Needs (dev only): pip install markdown playwright && python -m playwright install chromium
"""

import os
import markdown
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "docs", "solution_note.md")
OUT = os.path.join(BASE, "docs", "solution_note.pdf")

CSS = """
@page { size: A4; margin: 13mm 14mm 12mm 14mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 8.8pt; line-height: 1.36; color: #1a1a1a; margin: 0; }
.banner { background: linear-gradient(135deg, #1A1A1A 0%, #2D0005 55%, #8A000A 100%); color: #fff;
          padding: 9px 14px; border-radius: 6px; margin-bottom: 8px; }
.banner h1 { margin: 0; font-size: 16pt; letter-spacing: .2px; }
.banner p { margin: 2px 0 0; font-size: 8.8pt; opacity: .9; }
h2 { font-size: 10.6pt; color: #8A000A; margin: 9px 0 3px; padding-bottom: 2px; border-bottom: 1.5px solid #E8C4C8; }
p { margin: 3px 0; }
ul, ol { margin: 3px 0 3px 16px; padding: 0; }
li { margin: 1.5px 0; }
table { border-collapse: collapse; width: 100%; margin: 4px 0; font-size: 8.4pt; }
th { background: #F4E6E8; text-align: left; }
th, td { border: 1px solid #DDD; padding: 3px 6px; vertical-align: top; }
code { font-family: Consolas, monospace; font-size: 8pt; background: #F3F3F5; padding: 0 3px; border-radius: 3px; }
strong { color: #111; }
.flow { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin: 4px 0 6px; font-size: 8.2pt; color: #8A000A; }
.flow span { background: #F4E6E8; color: #1a1a1a; border-radius: 4px; padding: 2px 7px; }
.shots { display: flex; flex-direction: column; gap: 6px; margin: 4px 0; }
.shots figure { margin: 0; border: 1px solid #E3E3E3; border-radius: 6px; padding: 5px; }
.shots figure + figure img { width: 62%; margin: 0 auto; }
.shots img { width: 100%; display: block; }
figcaption { font-size: 7.8pt; color: #555; margin-top: 4px; }
"""

def main():
    with open(SRC, encoding="utf-8") as f:
        md = f.read()
    # Title block becomes a banner; the rest is rendered as-is
    lines = md.splitlines()
    title = lines[0].lstrip("# ").strip()
    subtitle = lines[1].strip("* ").strip() if len(lines) > 1 else ""
    body = markdown.markdown("\n".join(lines[2:]), extensions=["tables"])
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="banner"><h1>{title}</h1><p>{subtitle}</p></div>{body}</body></html>"""
    tmp = os.path.join(BASE, "docs", "_note.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        page = b.new_page()
        page.goto("file:///" + os.path.join(BASE, "docs", "_note.html").replace(os.sep, "/"))
        page.pdf(path=OUT, format="A4", print_background=True, prefer_css_page_size=True)
        b.close()
    os.remove(tmp)
    print(OUT)

if __name__ == "__main__":
    main()
