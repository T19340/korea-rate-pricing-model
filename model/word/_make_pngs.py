# -*- coding: utf-8 -*-
"""Word용 Exhibit PNG 생산 — 기존 make_figs*.py를 그대로 실행하되
Figure.savefig를 패치해 SVG와 함께 200dpi PNG도 저장한다."""
import runpy
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

_orig = Figure.savefig


def patched(self, fname, *a, **k):
    _orig(self, fname, *a, **k)
    p = Path(str(fname))
    if p.suffix == ".svg":
        k2 = dict(k)
        k2["dpi"] = 200
        _orig(self, p.with_suffix(".png"), *a, **k2)


Figure.savefig = patched

import os
os.chdir(SCRIPTS)
for script in ["make_figs.py", "make_figs_extra.py", "make_figs_validation.py"]:
    print("==", script)
    runpy.run_path(str(SCRIPTS / script), run_name="__main__")
print("done")
