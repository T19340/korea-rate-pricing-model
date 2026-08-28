# -*- coding: utf-8 -*-
"""docx → PDF(Word COM) → 페이지 PNG 검수 렌더. 경로를 인자로 받는다.

_verify_word.py는 대상 파일명이 박혀 있어 v16 문서만 검수할 수 있었다.
회의 회차마다 문서가 늘어나므로 인자로 받도록 분리한다.

    python _verify_any.py 8월금통위_사후검증.docx 8월금통위_이후_전망.docx

Word COM은 DispatchEx로 전용 인스턴스를 띄운다(떠 있는 창에 올라타면 사용자가
열어둔 문서 상태에 좌우된다). PNG는 파일명 앞자리를 따 접두어로 구분한다.
"""
import sys
from pathlib import Path

import fitz
import pythoncom
from win32com.client import DispatchEx

HERE = Path(__file__).resolve().parent
targets = [Path(a) if Path(a).is_absolute() else HERE / a for a in sys.argv[1:]]
if not targets:
    sys.exit("사용법: python _verify_any.py <docx> [<docx> ...]")

pythoncom.CoInitialize()
word = DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    for docx in targets:
        if not docx.exists():
            print(f"[SKIP] 없음: {docx.name}")
            continue
        stem = docx.stem
        pdf_path = HERE / f"_check_{stem}.pdf"
        doc = word.Documents.Open(str(docx), ReadOnly=True, AddToRecentFiles=False)
        doc.ExportAsFixedFormat(str(pdf_path), 17)
        n_word = doc.ComputeStatistics(2)   # wdStatisticPages
        doc.Close(0)

        pdf = fitz.open(pdf_path)
        print(f"\n=== {docx.name} ===")
        print(f"  페이지: {pdf.page_count} (Word 통계 {n_word})")
        for i, page in enumerate(pdf):
            png = HERE / f"_pg_{stem}_{i + 1}.png"
            page.get_pixmap(dpi=110).save(png)
        # 본문에서 빈 표·깨진 그림 자리를 잡아내기 위한 간단 점검
        blanks = [i + 1 for i, p in enumerate(pdf) if len(p.get_text().strip()) < 40]
        imgs = sum(len(p.get_images()) for p in pdf)
        print(f"  그림 개수: {imgs} · 사실상 빈 페이지: {blanks or '없음'}")
        pdf.close()
finally:
    word.Quit()
    pythoncom.CoUninitialize()
print("\ndone")
