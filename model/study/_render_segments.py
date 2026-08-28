# -*- coding: utf-8 -*-
"""구간별 렌더 검수: 음수 마진 사본을 만들어 뷰포트 단위로 스크린샷."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "step_method_study.html"
# Chrome은 64비트/32비트 두 경로 중 아무 데나 깔린다. 한쪽만 박아두면
# 다른 PC에서 조용히 실패한다.
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
CHROME = next((c for c in _CHROME_CANDIDATES if Path(c).exists()), None)
if CHROME is None:
    sys.exit("chrome.exe 를 찾지 못했습니다: " + " / ".join(_CHROME_CANDIDATES))

html = SRC.read_text(encoding="utf-8")
offsets = [int(a) for a in sys.argv[1:]] or list(range(0, 27500, 2500))

for off in offsets:
    seg = HERE / f"_seg_{off}.html"
    inj = (f"<style>body{{margin-top:-{off}px}} "
           ".panel-rail{position:static!important}</style></head>")
    seg.write_text(html.replace("</head>", inj), encoding="utf-8")
    png = HERE / f"_seg_{off}.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                    f"--user-data-dir={HERE / '_chrome_prof'}",
                    f"--screenshot={png}", "--window-size=1280,2800",
                    "--virtual-time-budget=30000", seg.as_uri()],
                   capture_output=True)
    print(png.name, png.stat().st_size if png.exists() else "FAIL")
    seg.unlink(missing_ok=True)
