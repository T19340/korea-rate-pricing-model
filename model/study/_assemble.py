# -*- coding: utf-8 -*-
"""step_method_study.html 조립기.

reference.html의 <head>+<style> (정본 그대로) + _body1~4.html 을 잇고,
<!--CELLBLOCK|label|header|n|note--> 자리에는 실행된 노트북의 n번째 코드 셀의
코드·표준출력을 그대로 삽입한다 — 계약 C2(코드 동일)·C3(출력 동일)의 기계적 보장.
"""
from __future__ import annotations

import html as htmlmod
import re
from pathlib import Path

import nbformat

HERE = Path(__file__).resolve().parent
OUT = HERE / "step_method_study.html"
TITLE = "시장이 매긴 금리인상 확률 — KOFR OIS 계단함수 학습 노트"

# ── 1. head + style: reference.html에서 </head>까지 그대로
ref = (HERE / "reference.html").read_text(encoding="utf-8")
head = ref.split("</head>")[0] + "</head>\n<body>\n"
head = re.sub(r"<title>.*?</title>", f"<title>{TITLE}</title>", head, count=1)

# ── 2. 노트북 코드 셀 (1-based) → (code, stdout)
nb = nbformat.read(HERE / "step_method_workbook.ipynb", as_version=4)
code_cells = [c for c in nb.cells if c.cell_type == "code"]
print(f"노트북 코드 셀 수: {len(code_cells)}")


def cell_block(label: str, header: str, idx: int, note: str) -> str:
    c = code_cells[idx - 1]
    code = htmlmod.escape(c.source.rstrip("\n"))
    outs = [o.get("text", "") for o in c.get("outputs", [])
            if o.get("output_type") == "stream"]
    stdout = htmlmod.escape("".join(outs).rstrip("\n"))
    parts = [f'<div class="cell">',
             f'  <div class="cell-hd">{header}</div>',
             f'<pre class="code">{code}</pre>']
    if note.strip():
        note_html = re.sub(r"`([^`]+)`", r"<code>\1</code>", note.strip())
        parts.append(f'  <div class="cell-note">{note_html}</div>')
    if stdout.strip():
        parts.append('  <details class="out"><summary>실행 결과</summary>'
                     f'<pre class="output">{stdout}</pre></details>')
    parts.append('</div>')
    return "\n".join(parts)


# ── 3. 본문 결합 + 플레이스홀더 치환
body = "\n".join((HERE / f"_body{i}.html").read_text(encoding="utf-8")
                 for i in (1, 2, 3, 4))

PAT = re.compile(r"<!--CELLBLOCK\|(.*?)\|(.*?)\|(\d+)\|(.*?)-->", re.S)
used = []


def repl(m):
    label, header, idx, note = m.group(1), m.group(2), int(m.group(3)), m.group(4)
    used.append(idx)
    return cell_block(label, header, idx, note)


body = PAT.sub(repl, body)
assert "CELLBLOCK" not in body, "치환되지 않은 플레이스홀더가 남아 있다"
print(f"삽입한 셀 블록: {sorted(used)}")

# ── 4. 검증: 본문의 모든 figs/ 이미지가 실재하는가
missing = [s for s in re.findall(r'src="(figs/[^"]+)"', body)
           if not (HERE / s).exists()]
assert not missing, f"없는 그림: {missing}"

OUT.write_text(head + body + "\n</body>\n</html>\n", encoding="utf-8")
print(f"저장: {OUT} ({OUT.stat().st_size:,} bytes)")
print(f".cell 개수: {body.count('class=\"cell\"')}")
