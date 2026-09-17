"""draft.md → report.html (읽는 문서. 영상은 넣지 않는다 — 내려받고 인쇄하는 독립 문서) + report.json (앱·퀴즈·만화용 구조화 데이터)

사용: python render.py <작업 폴더>
템플릿: ../assets/report-template.html
"""
import base64
import html
import json
import re
import sys
from pathlib import Path

from common import TS_RE, TYPES, load_inputs, parse_report, screen_at, to_sec, to_ts

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "report-template.html"
SECTION_CLASS = {"결정 사항": "decisions", "액션 아이템": "actions", "영상 속 자료와 발언이 다른 부분": "conflicts"}
# 섹션 제목 아래에 붙는 안내문. 독자가 "분석이 틀렸나?" 하고 오해하지 않게 한다.
SECTION_NOTE = {
    "영상 속 자료와 발언이 다른 부분": "영상에 나온 화면 자료(슬라이드, 문서, 대시보드 등)에 적힌 내용과 사람이 실제로 말한 내용이 서로 달랐던 곳입니다. 분석 오류가 아니라 영상 자체에 있는 불일치이며, 어느 쪽이 맞는지는 판단하지 않고 둘 다 적었습니다.",
}
THUMBS_PER_SECTION = 2
CLOSE = {"ul": "</ul>", "table": "</tbody></table></div>"}


def inline(text: str) -> str:
    """항목 한 줄의 마크다운 → HTML. 타임스탬프는 영상 이동 링크가 된다."""
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)

    def link(m):
        start = to_sec(m.group(1))
        return f'<a class="ts" href="#t={start}" data-t="{start}">{m.group(0)[1:-1]}</a>'

    return TS_RE.sub(link, out)


def data_uri(path: Path) -> str:
    """이미지를 문서 안에 담는다. report.html 하나만 내려받아도 그림이 깨지지 않게."""
    kind = "png" if path.suffix.lower() == ".png" else "jpeg"
    return f"data:image/{kind};base64," + base64.b64encode(path.read_bytes()).decode()


def thumbs(work, screens, items):
    """섹션이 인용한 시각의 화면 중 이미지가 있는 것 몇 장. 사람이나 참가자 이름표가 나온 화면은 뺀다."""
    picked = []
    for it in items:
        for ts in it["timestamps"]:
            sc = screen_at(screens, ts["start"])
            if not sc or sc.get("kind") in ("people", "participants") or not sc.get("image"):
                continue
            if sc["image"] not in [p["image"] for p in picked] and (work / sc["image"]).exists():
                picked.append(sc)
    if not picked:
        return ""
    figs = "".join(
        f'<a class="ts thumb" href="#t={int(sc["time"])}" data-t="{int(sc["time"])}">'
        f'<img src="{data_uri(work / sc["image"])}" alt="{html.escape(sc.get("description", ""))}">'
        f"<span>{to_ts(sc['time'])}</span></a>"
        for sc in picked[:THUMBS_PER_SECTION]
    )
    return f'<div class="thumbs">{figs}</div>'


def main():
    work = Path(sys.argv[1])
    report = parse_report((work / "draft.md").read_text(encoding="utf-8"))
    _, screens, duration = load_inputs(work)

    body, data_sections, n, last_header = [], [], 0, None
    open_section = False
    for sec in report["sections"]:
        if sec["level"] == 2:
            if open_section:
                body.append("</section>")
            cls = SECTION_CLASS.get(sec["heading"], "")
            sid = sum(1 for x in body if x.startswith("<section")) + 1  # 바깥 화면의 목차가 이 id로 찾아온다 (s1, s2, …)
            body.append(f'<section class="{cls}" id="s{sid}"><h2>{html.escape(sec["heading"])}</h2>')
            if sec["heading"] in SECTION_NOTE:
                body.append(f'<p class="note">{SECTION_NOTE[sec["heading"]]}</p>')
            open_section = True
        else:
            body.append(f"<h3>{html.escape(sec['heading'])}</h3>")
        body.append(thumbs(work, screens, sec["items"]))
        items = []
        mode = None  # 지금 열려 있는 묶음: "ul" 또는 "table"
        for it in sec["items"]:
            n += 1
            pid = f"p{n}"
            want = "table" if "cells" in it else "ul"
            if want != mode or (want == "table" and it["header"] is not last_header):
                body.append(CLOSE.get(mode, ""))
                if want == "table":
                    heads = "".join(f"<th>{inline(c)}</th>" for c in it["header"])
                    body.append(f'<div class="table-wrap"><table><thead><tr>{heads}</tr></thead><tbody>')
                else:
                    body.append("<ul>")
                mode, last_header = want, it.get("header")
            if want == "table":
                tds = "".join(f"<td>{inline(c)}</td>" for c in it["cells"])
                body.append(f'<tr id="{pid}">{tds}</tr>')
            else:
                body.append(f'<li id="{pid}">{inline(it["text"])}</li>')
            entry = {"id": pid, "text": TS_RE.sub("", it["text"]).strip(" —"), "timestamps": it["timestamps"]}
            if want == "table":  # 열 이름을 살려 둔다 — 퀴즈가 "no-cache의 저장 여부" 같은 구조를 쓸 수 있게
                entry["fields"] = {h: TS_RE.sub("", c).strip() for h, c in zip(it["header"], it["cells"]) if TS_RE.sub("", c).strip()}
            items.append(entry)
        body.append(CLOSE.get(mode, ""))
        data_sections.append({"heading": sec["heading"], "level": sec["level"], "items": items})
    if open_section:
        body.append("</section>")

    kind = report["meta"].get("type", "general")

    page = TEMPLATE.read_text(encoding="utf-8")
    for key, value in {
        "{{title}}": html.escape(report["title"] or "리포트"),
        "{{type_label}}": TYPES.get(kind, kind),
        "{{duration}}": to_ts(duration),
        "{{summary}}": inline(report["summary"]),
        "{{body}}": "\n".join(b for b in body if b),
    }.items():
        page = page.replace(key, value)
    (work / "report.html").write_text(page, encoding="utf-8")

    (work / "report.json").write_text(
        json.dumps(
            {"title": report["title"], "type": kind, "duration": duration,
             "summary": report["summary"], "sections": data_sections},
            ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{work / 'report.html'}\n{work / 'report.json'} (항목 {n}개)")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
