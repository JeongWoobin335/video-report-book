"""작업 폴더의 결과물들로 가는 index.html과, 영상 옆에 문서를 놓고 보는 watch.html을 만든다.

사용: python make_index.py <작업 폴더>
"""
import html
import json
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TEMPLATE = ASSETS / "index-template.html"
TYPES = {"meeting": "회의", "education": "교육·강의", "general": "일반"}


def main():
    work = Path(sys.argv[1])
    if not (work / "report.json").exists():
        sys.exit(f"{work / 'report.json'} 가 없습니다. 리포트부터 만드세요.")
    report = json.loads((work / "report.json").read_text(encoding="utf-8"))

    def count(name, key):
        f = work / name
        return len(json.loads(f.read_text(encoding="utf-8"))[key]) if f.exists() else None

    n_items = sum(len(s["items"]) for s in report["sections"])
    n_quiz, n_comic = count("quiz.json", "items"), count("comic.json", "panels")
    meeting = report["type"] == "meeting"
    cards = [("report.html", "📄", "통합 리포트", f"항목 {n_items}개 · 모든 항목에 영상 시각")]
    if n_quiz and (work / "quiz.html").exists():
        cards.append(("quiz.html", "✅", "내용 확인" if meeting else "이해도 퀴즈", f"{n_quiz}문항 · 틀리면 다시 볼 구간 안내"))
    if n_comic and (work / "comic.html").exists():
        cards.append(("comic.html", "💬", "만화 요약", f"{n_comic}컷 · 가볍게 훑어보기"))

    # 영상 파일이 작업 폴더에 있으면 "영상과 함께 보기" 화면도 만든다. 리포트 자체에는 영상을 넣지 않는다(내려받는 문서라서).
    video = next((p.name for p in work.glob("video.*") if p.suffix.lower() in {".mp4", ".webm", ".mov", ".m4v"}), None)
    if video:
        tabs = "".join(f'<button data-src="{href}"{" class=on" if i == 0 else ""}>{html.escape(name)}</button>'
                       for i, (href, _, name, _) in enumerate(cards))
        watch = (ASSETS / "watch-template.html").read_text(encoding="utf-8")
        for key, value in {"{{title}}": html.escape(report["title"]), "{{video}}": html.escape(video), "{{tabs}}": tabs, "{{first}}": cards[0][0]}.items():
            watch = watch.replace(key, value)
        (work / "watch.html").write_text(watch, encoding="utf-8")
        cards.insert(0, ("watch.html", "🎬", "영상과 함께 보기", "영상 옆에 리포트·퀴즈·만화 — 시각을 누르면 그 장면으로"))

    d = int(report["duration"])
    page = TEMPLATE.read_text(encoding="utf-8")
    for key, value in {
        "{{title}}": html.escape(report["title"]),
        "{{meta}}": f"{TYPES.get(report['type'], report['type'])} · 영상 길이 {d // 60}분 {d % 60}초",
        "{{summary}}": re.sub(r"`(.+?)`", r"<code>\1</code>", html.escape(report["summary"])),
        "{{cards}}": "\n".join(
            f'<a class="card" href="{href}"><span class="icon">{icon}</span><strong>{html.escape(name)}</strong><span>{html.escape(desc)}</span></a>'
            for href, icon, name, desc in cards),
    }.items():
        page = page.replace(key, value)
    (work / "index.html").write_text(page, encoding="utf-8")
    print(f"{work / 'index.html'} — " + ", ".join(c[2] for c in cards))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
