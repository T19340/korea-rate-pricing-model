# -*- coding: utf-8 -*-
"""Assemble report.html: inline the SVG exhibits into the template."""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
template = (BASE / "report_template.html").read_text(encoding="utf-8")

def clean_svg(path: Path) -> str:
    svg = path.read_text(encoding="utf-8")
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
    # charts scale via CSS width:100% + viewBox; equations keep their
    # intrinsic pt size (capped by max-width in CSS)
    if not path.name.startswith("eq"):
        svg = re.sub(r'(<svg[^>]*?)\s+width="[^"]*"\s+height="[^"]*"', r"\1",
                     svg, count=1)
    return svg.strip()

for m in re.findall(r"<!--SVG:([^>]+?)-->", template):
    svg_path = BASE / "figs" / m
    template = template.replace(f"<!--SVG:{m}-->", clean_svg(svg_path))

out = BASE / "report.html"
out.write_text(template, encoding="utf-8")
print("wrote", out, f"({out.stat().st_size / 1024:.0f} KB)")
