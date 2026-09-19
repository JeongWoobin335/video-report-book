"""화면 파일 주소에 버전 꼬리표(?v=…)를 붙인다. 화면(web/)을 고친 뒤 올리기 전에 한 번 돌린다.

    python tools/stamp_version.py

GitHub Pages는 파일을 10분 동안 캐시하게 하고, 브라우저는 그보다 오래 붙들기도 한다.
그래서 새 index.html에 옛 app.css가 입혀져 화면이 깨지는 일이 생긴다(2026-09-20에 실제로 겪음).
꼬리표가 바뀌면 브라우저는 다른 파일로 보고 새로 받는다 — html과 css·js가 늘 같은 판으로 맞는다.
"""
import re
import sys
import time
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
# (파일, 그 안에서 꼬리표를 붙일 주소들)
TARGETS = {
    "index.html": ["css/app.css", "js/app.js", "vendor/lame.min.js"],
    "js/app.js": ["./config.js", "./preprocess.js", "demo/status.json", "demo/quiz.json"],
    "lab/preprocess.html": ["../vendor/lame.min.js", "../js/preprocess.js"],
}


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d%H%M")
    for name, urls in TARGETS.items():
        path = WEB / name
        text = path.read_text(encoding="utf-8")
        for url in urls:
            text, n = re.subn(re.escape(url) + r"(\?v=[\w.-]+)?(?=[\"'`])", f"{url}?v={version}", text)
            if not n:
                print(f"  (없음) {name}: {url}")
        if name == "js/app.js":  # 예시 결과물(demo/의 리포트·만화)도 같은 판으로 받게
            text = re.sub(r'const ASSET_V = "[^"]*";', f'const ASSET_V = "{version}";', text)
        path.write_text(text, encoding="utf-8", newline="\n")
    print("버전", version)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        _s.reconfigure(encoding="utf-8")
    main()
