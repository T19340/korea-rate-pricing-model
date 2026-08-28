# -*- coding: utf-8 -*-
"""자립화 빌드 — step_method_study_standalone.html 생성.

파일 하나만 보내도 그림·수식이 나오게: 그림 base64 내장 + 로컬 MathJax 인라인.
(스킬의 build_standalone.py는 CDN 참조 전용이라 로컬 mathjax 참조용으로 변형.)
"""
import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "step_method_study.html"
OUT = HERE / "step_method_study_standalone.html"

html = SRC.read_text(encoding="utf-8")


def img_sub(m):
    rel = m.group(1)
    if rel.startswith(("data:", "http")) or not rel.endswith(".png"):
        return m.group(0)
    f = HERE / rel
    data = base64.b64encode(f.read_bytes()).decode("ascii")
    return 'src="data:image/png;base64,' + data + '"'


html, _ = re.subn(r'src="([^"]+)"', img_sub, html)
print("이미지 내장:", html.count("data:image/png"))

mj = (HERE / "mathjax-tex-svg-full.js").read_text(encoding="utf-8")
if "</script" in mj:
    mj = mj.replace("</script", "<\\/script")
tag = '<script src="mathjax-tex-svg-full.js" id="MathJax-script"></script>'
assert tag in html
html = html.replace(tag, '<script id="MathJax-script">\n' + mj + "\n</script>")
print("MathJax 인라인: %.1f MB" % (len(mj) / 1e6))

OUT.write_text(html, encoding="utf-8")
print("저장:", OUT, "%.1f MB" % (OUT.stat().st_size / 1e6))
