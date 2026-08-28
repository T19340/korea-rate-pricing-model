# -*- coding: utf-8 -*-
"""Dump executed-notebook stdout per code cell (for HTML details.out copying)."""
from pathlib import Path
import nbformat

HERE = Path(__file__).resolve().parent
nb = nbformat.read(HERE / "step_method_workbook.ipynb", as_version=4)
out = []
ci = 0
for c in nb.cells:
    if c.cell_type != "code":
        continue
    ci += 1
    out.append(f"{'='*70}\nCODE CELL #{ci} (first line: {c.source.splitlines()[0] if c.source else ''})\n{'='*70}")
    for o in c.get("outputs", []):
        if o.get("output_type") == "stream":
            out.append(o.get("text", ""))
        elif o.get("output_type") == "error":
            out.append("ERROR: " + o.get("ename", ""))
(HERE / "_cell_outputs.txt").write_text("\n".join(out), encoding="utf-8")
print("written _cell_outputs.txt")
