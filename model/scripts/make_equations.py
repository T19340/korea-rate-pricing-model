# -*- coding: utf-8 -*-
"""Pre-render the display equations to self-contained SVGs (no CDN, no JS).

matplotlib mathtext with svg.fonttype='path' turns every glyph into vector
paths, so the formulas render identically on any machine, offline included.
The click-to-copy LaTeX stays on the wrapper div via data-latex.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import FIGS

FIGS.mkdir(parents=True, exist_ok=True)
INK = "#1A1A1A"

EQUATIONS = {
    "eq1_ois.svg":
        r"$F(T)\ \approx\ \frac{1}{T}\sum_{s=1}^{T} r(s),"
        r"\qquad r(s)\ =\ r_0+\sum_{k}\Delta_k\,\mathbf{1}\{s\geq m_k\}$",
    "eq2_prob.svg":
        r"$P_k\ =\ \mathrm{min}\left(\mathrm{max}\left("
        r"\Delta_k\,/\,25\,\mathrm{bp},\ 0\right),\ 1\right)$",
    "eq3_dns.svg":
        r"$y_t(\tau)\ =\ L_t+S_t\,\frac{1-e^{-\lambda\tau}}{\lambda\tau}"
        r"+C_t\left(\frac{1-e^{-\lambda\tau}}{\lambda\tau}"
        r"-e^{-\lambda\tau}\right)$",
    "eq4_shock.svg":
        r"$\Delta y(\tau)\ =\ \Delta S\cdot"
        r"\frac{1-e^{-\lambda\tau}}{\lambda\tau},\qquad \lambda=0.55$",
}

plt.rcParams.update({"svg.fonttype": "path", "mathtext.fontset": "cm"})

for name, tex in EQUATIONS.items():
    fig = plt.figure(figsize=(7.0, 0.9))
    fig.patch.set_alpha(0.0)
    fig.text(0.5, 0.5, tex, ha="center", va="center", fontsize=17, color=INK)
    fig.savefig(FIGS / name, bbox_inches="tight", pad_inches=0.08,
                transparent=True)
    plt.close(fig)
    print("saved", name)
