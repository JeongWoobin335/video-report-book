"""quiz-draft.md를 검사하고 quiz.json + quiz.html을 만든다.

사용: python build_quiz.py <작업 폴더>
읽는 것: quiz-draft.md, report.json
쓰는 것: quiz.json (정답 포함 — 서버·채점용), quiz.public.json (정답·해설 없음 — 응시자에게 내려보내는 용),
        quiz.html (혼자 풀어보는 화면. 정답이 페이지 안에 들어 있으므로 이수 확인용으로는 쓰지 않는다)
오류가 있으면 아무것도 쓰지 않고 종료 코드 1. 경고는 알려주기만 한다.
"""
import hashlib
import json
import random
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "quiz-template.html"
CHECKS = {"기억": "recall", "이해": "understanding"}
NO_QUIZ_SECTIONS = {"영상 속 자료와 발언이 다른 부분"}  # 정답에 다툼의 여지가 있는 곳
BANNED_CHOICES = ("위의 모두", "모두 정답", "모두 맞", "정답 없음", "해당 없음")
REVIEW_TAIL = 30  # 근거 항목에 구간 끝이 없을 때, 시작점에서 이만큼을 다시 볼 구간으로 잡는다(초)


def load_report(work: Path):
    """report.json → {항목 id: {top(최상위 섹션), section(그 항목이 속한 소주제), text, timestamps}}"""
    report = json.loads((work / "report.json").read_text(encoding="utf-8"))
    items, top = {}, None
    for sec in report["sections"]:
        if sec["level"] == 2:
            top = sec["heading"]
        for it in sec["items"]:
            items[it["id"]] = {"top": top, "section": sec["heading"], "text": it["text"], "timestamps": it["timestamps"]}
    # 자료와 발언이 달랐던 시각들. 그 섹션 밖의 본문 항목이 같은 내용을 담고 있을 수 있다.
    disputed = {t["start"] for it in items.values() if it["top"] in NO_QUIZ_SECTIONS for t in it["timestamps"]}
    for it in items.values():
        it["points_to_dispute"] = it["top"] not in NO_QUIZ_SECTIONS and "다른 부분" in it["text"]
        it["near_dispute"] = " / ".join(d["text"] for d in items.values() if d["top"] in NO_QUIZ_SECTIONS
                                        and any(t["start"] == u["start"] for t in it["timestamps"] for u in d["timestamps"]))             if it["top"] not in NO_QUIZ_SECTIONS else ""
    return report, items


def parse_draft(text: str):
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip("\"'")
        text = text[m.end():]

    questions, q, field = [], None, None
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^##\s+", line):
            q = {"label": line.lstrip("# ").strip(), "choices": []}
            questions.append(q)
            field = None
        elif q is None or not line:
            continue
        elif c := re.match(r"^[-*]\s*\[( |x|X)\]\s*(.+)", line):
            q["choices"].append({"text": c.group(2).strip(), "correct": c.group(1) != " "})
            field = None
        elif kv := re.match(r"^(확인|근거|문제|해설)\s*:\s*(.*)", line):
            field = kv.group(1)
            q[field] = kv.group(2).strip()
        elif field in ("문제", "해설"):  # 여러 줄에 걸친 문제·해설
            q[field] += " " + line
    return meta, questions


def main():
    work = Path(sys.argv[1])
    for name in ("quiz-draft.md", "report.json"):
        if not (work / name).exists():
            sys.exit(f"{work / name} 가 없습니다.")
    report, items = load_report(work)
    meta, questions = parse_draft((work / "quiz-draft.md").read_text(encoding="utf-8"))

    errors, warnings = [], []
    if not questions:
        errors.append("문항이 없습니다 ('## Q1' 형식의 제목으로 시작).")
    for q in questions:
        tag = q["label"]
        for key in ("확인", "근거", "문제", "해설"):
            if not q.get(key):
                errors.append(f"[{tag}] '{key}:' 줄이 없습니다.")
        if q.get("확인") and q["확인"] not in CHECKS:
            errors.append(f"[{tag}] 확인은 {' / '.join(CHECKS)} 중 하나여야 합니다.")

        q["sources"] = [s.strip() for s in q.get("근거", "").split(",") if s.strip()]
        for sid in q["sources"]:
            if sid not in items:
                errors.append(f"[{tag}] 근거 {sid} 가 report.json에 없습니다.")
            elif "(확인 필요)" in items[sid]["text"]:
                errors.append(f"[{tag}] 근거 {sid} 는 '(확인 필요)'로 표시된 불확실한 내용이라 출제할 수 없습니다.")
            elif items[sid]["points_to_dispute"]:
                errors.append(f"[{tag}] 근거 {sid} 는 자료와 발언이 달랐던 내용을 담은 항목이라 출제할 수 없습니다.")
            elif items[sid]["top"] in NO_QUIZ_SECTIONS:
                errors.append(f"[{tag}] 근거 {sid} 는 '{items[sid]['top']}' 섹션이라 출제할 수 없습니다.")
            elif items[sid]["near_dispute"]:
                warnings.append(f"[{tag}] 근거 {sid} 와 같은 시각에 자료와 발언이 달랐던 내용이 있습니다 — \"{items[sid]['near_dispute']}\" 이 어긋난 값을 문제·보기·해설에 쓰지 마세요.")
            elif "슬라이드에만" in items[sid]["text"]:
                warnings.append(f"[{tag}] 근거 {sid} 는 슬라이드에만 있던 내용입니다. 영상을 듣기만 한 사람에게 불공정할 수 있습니다.")

        texts = [c["text"] for c in q["choices"]]
        if len(texts) != 4:
            errors.append(f"[{tag}] 보기는 4개여야 합니다 (지금 {len(texts)}개).")
        if sum(c["correct"] for c in q["choices"]) != 1:
            errors.append(f"[{tag}] 정답([x])은 정확히 1개여야 합니다.")
        if len(set(texts)) != len(texts):
            errors.append(f"[{tag}] 같은 보기가 두 번 나옵니다.")
        for t in texts:
            if any(b in t for b in BANNED_CHOICES):
                errors.append(f"[{tag}] '{t}' 같은 보기는 내용을 몰라도 요령으로 풀게 만듭니다.")
        right = [c["text"] for c in q["choices"] if c["correct"]]
        wrong = [c["text"] for c in q["choices"] if not c["correct"]]
        if right and wrong and len(right[0]) > 1.6 * max(len(w) for w in wrong):
            warnings.append(f"[{tag}] 정답이 다른 보기보다 눈에 띄게 깁니다. 길이를 맞추세요.")

    if questions and not errors:
        by_section = {}
        for q in questions:
            sec = items[q["sources"][0]]["section"]
            by_section[sec] = by_section.get(sec, 0) + 1
        sec, n = max(by_section.items(), key=lambda x: x[1])
        if len(questions) >= 6 and n > len(questions) / 2:
            warnings.append(f"문항 {len(questions)}개 중 {n}개가 '{sec}'에서 나왔습니다. 영상 전체에 고르게 퍼지게 하세요.")
        starts = [min(t["start"] for s in q["sources"] for t in items[s]["timestamps"]) for q in questions]
        if len(questions) >= 6 and max(starts) < report["duration"] * 0.6:
            warnings.append("영상 뒤쪽 40%에서 나온 문항이 없습니다.")

    for w in warnings:
        print("경고:", w)
    if errors:
        print(f"오류 {len(errors)}개 — quiz.json을 만들지 않았습니다.")
        for e in errors:
            print(" -", e)
        sys.exit(1)

    # 정답 위치를 고르게 섞는다. 같은 초안이면 늘 같은 결과가 나오도록 제목으로 시드를 잡는다.
    title = meta.get("title") or f"{report['title']} — 이해도 확인"
    rng = random.Random(int(hashlib.sha256(title.encode()).hexdigest(), 16))
    slots = [i % 4 for i in range(len(questions))]
    rng.shuffle(slots)

    out = []
    for n, (q, slot) in enumerate(zip(questions, slots), 1):
        wrong = [c["text"] for c in q["choices"] if not c["correct"]]
        rng.shuffle(wrong)
        ordered = wrong[:slot] + [c["text"] for c in q["choices"] if c["correct"]] + wrong[slot:]
        stamps = [t for s in q["sources"] for t in items[s]["timestamps"]]
        start = min(t["start"] for t in stamps)
        end = max((t["end"] or t["start"] + REVIEW_TAIL) for t in stamps)
        out.append({
            "id": f"q{n}",
            "checks": CHECKS[q["확인"]],
            "question": q["문제"],
            "choices": [{"id": "abcd"[i], "text": t} for i, t in enumerate(ordered)],
            "answer": "abcd"[slot],
            "explanation": q["해설"],
            "sources": q["sources"],
            "section": items[q["sources"][0]]["section"],
            "review": {"start": start, "end": min(end, report["duration"])},
        })

    quiz = {"title": title, "type": report["type"], "report_title": report["title"], "items": out}
    (work / "quiz.json").write_text(json.dumps(quiz, ensure_ascii=False, indent=2), encoding="utf-8")
    public = dict(quiz, items=[{k: v for k, v in it.items() if k in ("id", "checks", "question", "choices")} for it in out])
    (work / "quiz.public.json").write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    page = TEMPLATE.read_text(encoding="utf-8").replace("{{title}}", title.replace("<", "&lt;"))
    page = page.replace("{{quiz_json}}", json.dumps(quiz, ensure_ascii=False).replace("</", "<\\/"))
    (work / "quiz.html").write_text(page, encoding="utf-8")

    kinds = [q["checks"] for q in out]
    print(f"문항 {len(out)}개 (기억 {kinds.count('recall')} · 이해 {kinds.count('understanding')}), 경고 {len(warnings)}개")
    print(work / "quiz.json")
    print(work / "quiz.html")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
