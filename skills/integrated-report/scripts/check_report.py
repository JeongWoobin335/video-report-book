"""draft.md의 형식을 검사하고, 항목마다 그 시각의 원문을 나란히 뽑는다.

사용: python check_report.py <작업 폴더>
출력: 오류 목록(표준 출력), evidence.md. 오류가 있으면 종료 코드 1.
"""
import sys
from pathlib import Path

from common import TYPES, load_inputs, parse_report, screen_at, to_ts

BEFORE, AFTER = 5, 25  # 타임스탬프 앞뒤로 원문을 보여줄 범위(초)


def main():
    work = Path(sys.argv[1])
    report_path = work / "draft.md"
    if not report_path.exists():
        sys.exit(f"{report_path} 가 없습니다.")
    segments, screens, duration = load_inputs(work)
    report = parse_report(report_path.read_text(encoding="utf-8"))

    errors = []
    if not report["title"]:
        errors.append("제목이 없습니다 (frontmatter의 title 또는 '# 제목').")
    if report["meta"].get("type") not in TYPES:
        errors.append(f"frontmatter의 type은 {', '.join(TYPES)} 중 하나여야 합니다.")
    if not report["summary"]:
        errors.append("'## 한눈에 보기'가 비어 있습니다.")

    shown = {}  # 이미 원문을 보여준 (시작, 끝) → 항목 번호
    ev = ["# 근거 대조", "", "항목마다 원문이 정말 그 말을 하고 있는지 확인한다.", ""]
    count = 0
    sections = report["sections"]
    for i, sec in enumerate(sections):
        # '##' 아래에 바로 '###'가 오는 경우만 빈 채로 둘 수 있다
        has_children = sec["level"] == 2 and i + 1 < len(sections) and sections[i + 1]["level"] == 3
        if not sec["items"] and not has_children:
            errors.append(f"[{sec['heading']}] 섹션이 비어 있습니다 — 내용이 없으면 섹션을 빼세요.")
        for it in sec["items"]:
            short = it["text"][:50]
            if it.get("prose"):
                errors.append(f"[{sec['heading']}] 불릿이 아닌 줄글: \"{short}…\"")
                continue
            count += 1
            if not it["timestamps"]:
                errors.append(f"[{sec['heading']}] 타임스탬프 없음: \"{short}…\"")
                continue
            ev += [f"## {count}. {sec['heading']}", "", f"> {it['text']}", ""]
            for ts in it["timestamps"]:
                start, end = ts["start"], ts["end"]
                if start > duration or (end and end > duration):
                    errors.append(f"[{sec['heading']}] 영상 길이({to_ts(duration)})를 벗어난 시각: \"{short}…\"")
                    continue
                if end is not None and end < start:
                    errors.append(f"[{sec['heading']}] 구간의 끝이 시작보다 앞섬: \"{short}…\"")
                    continue
                lo, hi = start - BEFORE, (end or start) + AFTER
                if (start, end) in shown:  # 같은 시각을 근거로 든 항목이 많으면 같은 원문이 반복돼 아무도 안 읽게 된다
                    ev += [f"**[{to_ts(start)}] 부근** — 위 {shown[(start, end)]}번 항목과 같은 원문", ""]
                    continue
                shown[(start, end)] = count
                ev.append(f"**[{to_ts(start)}] 부근**")
                sc = screen_at(screens, start)
                if sc:
                    text = " / ".join((sc.get("text") or "").split("\n"))[:300]
                    ev.append(f"- 화면({sc.get('kind', 'other')}): {text or sc.get('description', '')}")
                near = [s for s in segments if s["end"] >= lo and s["start"] <= hi]
                for s in near:
                    who = f"{s['speaker']}: " if s.get("speaker") else ""
                    ev.append(f"- [{to_ts(s['start'])}] {who}{s['text']}")
                if not near and not sc:
                    errors.append(f"[{sec['heading']}] {to_ts(start)} 부근에 발화도 화면도 없음: \"{short}…\"")
                ev.append("")

    (work / "evidence.md").write_text("\n".join(ev), encoding="utf-8")
    print(f"항목 {count}개 검사, 오류 {len(errors)}개")
    for e in errors:
        print(" -", e)
    print(f"근거 대조: {work / 'evidence.md'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
