"""answers/*.json을 채점해 results/<응답자>.json을 만든다.

사용: python grade.py <작업 폴더>
읽는 것: quiz.json, answers/*.json     쓰는 것: results/*.json
"""
import json
import re
import sys
from pathlib import Path

MERGE_GAP = 10  # 다시 볼 구간 사이가 이보다 가까우면 하나로 합친다(초)


def to_ts(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def merge_spans(spans):
    """[{start, end, ...}] → 겹치거나 가까운 구간을 합친 목록. 나머지 키는 목록으로 모은다."""
    merged = []
    for sp in sorted(spans, key=lambda x: x["start"]):
        if merged and sp["start"] <= merged[-1]["end"] + MERGE_GAP:
            last = merged[-1]
            last["end"] = max(last["end"], sp["end"])
            last["items"] += sp["items"]
        else:
            merged.append({"start": sp["start"], "end": sp["end"], "items": list(sp["items"])})
    for sp in merged:
        sp["label"] = f"{to_ts(sp['start'])}–{to_ts(sp['end'])}"
    return merged


def grade_one(quiz, response):
    given = response.get("answers", {})
    rows, by_checks, by_section = [], {}, {}
    for q in quiz["items"]:
        ok = given.get(q["id"]) == q["answer"]  # 응답하지 않은 문항은 틀린 것으로 센다
        rows.append({"id": q["id"], "given": given.get(q["id"]), "answer": q["answer"], "correct": ok})
        for table, key in ((by_checks, q["checks"]), (by_section, q["section"])):
            t = table.setdefault(key, {"correct": 0, "total": 0})
            t["correct"] += ok
            t["total"] += 1
    missed = [q for q, r in zip(quiz["items"], rows) if not r["correct"]]
    spans = merge_spans([{"start": q["review"]["start"], "end": q["review"]["end"], "items": [q["id"]]} for q in missed])
    return {
        "respondent": response.get("respondent", "익명"),
        "submitted_at": response.get("submitted_at"),
        "correct": sum(r["correct"] for r in rows),
        "total": len(rows),
        "items": rows,
        "by_checks": by_checks,
        "by_section": by_section,
        "review_spans": spans,
        "review_seconds": sum(sp["end"] - sp["start"] for sp in spans),
        "missed": [{"id": q["id"], "question": q["question"], "explanation": q["explanation"]} for q in missed],
    }


def grade_all(work: Path):
    quiz = json.loads((work / "quiz.json").read_text(encoding="utf-8"))
    files = sorted((work / "answers").glob("*.json"))
    if not files:
        sys.exit(f"{work / 'answers'} 에 응답 파일이 없습니다.")
    out = work / "results"
    out.mkdir(exist_ok=True)
    results = []
    for f in files:
        res = grade_one(quiz, json.loads(f.read_text(encoding="utf-8")))
        name = re.sub(r"[^\w가-힣-]+", "_", res["respondent"]) or f.stem
        (out / f"{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(res)
    return quiz, results


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    quiz, results = grade_all(Path(sys.argv[1]))
    meeting = quiz["type"] == "meeting"
    for r in results:
        spans = ", ".join(sp["label"] for sp in r["review_spans"]) or "없음"
        head = f"다시 확인할 부분 {r['total'] - r['correct']}곳" if meeting else f"{r['correct']}/{r['total']}"
        print(f"{r['respondent']}: {head} · 다시 볼 구간 {spans} (총 {r['review_seconds']}초)")
    print(f"→ {Path(sys.argv[1]) / 'results'} ({len(results)}명)")
