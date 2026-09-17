"""채점 결과를 모아 summary.json을 만들고, insights.md가 있으면 그것까지 넣어 summary.html을 만든다.

사용: python summarize.py <작업 폴더>
읽는 것: quiz.json, answers/*.json, (있으면) insights.md     쓰는 것: results/*.json, summary.json, summary.html
"""
import html
import json
import re
import sys
from pathlib import Path

from grade import grade_all, merge_spans

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "summary-template.html"
LOW = 0.5          # 이보다 낮은 정답률이면 'low'
HOT = 0.6          # 이보다 낮은 문항의 구간을 '많이 틀린 구간'으로 모은다
STRONG_MISS_MIN = 6  # 상·하위 비교는 이 인원 이상일 때만


def rate(c, t):
    return round(c / t, 2) if t else None


def summarize(quiz, results):
    n = len(results)
    ranked = sorted(results, key=lambda r: -r["correct"])
    top, bottom = ranked[: n // 2], ranked[n - n // 2:]
    items = []
    for i, q in enumerate(quiz["items"]):
        picks = {c["id"]: 0 for c in q["choices"]}
        picks["(무응답)"] = 0
        for r in results:
            g = r["items"][i]["given"]
            picks[g if g in picks else "(무응답)"] += 1
        right = picks[q["answer"]]
        wrong = {k: v for k, v in picks.items() if k != q["answer"] and v}
        top_wrong = max(wrong.items(), key=lambda x: x[1]) if wrong else None
        text = {c["id"]: c["text"] for c in q["choices"]}
        flags = []
        if right / n < LOW:
            flags.append("low")
        if top_wrong and top_wrong[1] > right:
            flags.append("wrong_beats_right")
        n_wrong = n - right
        if n_wrong >= 3 and top_wrong and top_wrong[1] <= n_wrong / 2:
            flags.append("scattered")
        if n >= STRONG_MISS_MIN:
            t = sum(r["items"][i]["correct"] for r in top) / len(top)
            b = sum(r["items"][i]["correct"] for r in bottom) / len(bottom)
            if t < b:
                flags.append("strong_miss")
        items.append({
            "id": q["id"], "question": q["question"], "checks": q["checks"], "section": q["section"],
            "correct_rate": rate(right, n), "answer": q["answer"], "answer_text": text[q["answer"]],
            "choices": [{"id": k, "text": text.get(k, ""), "count": v} for k, v in picks.items() if v or k in text],
            "top_wrong": {"id": top_wrong[0], "text": text.get(top_wrong[0], ""), "count": top_wrong[1]} if top_wrong else None,
            "review": q["review"], "flags": flags,
        })

    def pooled(key):
        table = {}
        for r in results:
            for k, v in r[key].items():
                t = table.setdefault(k, [0, 0])
                t[0] += v["correct"]
                t[1] += v["total"]
        return {k: rate(*v) for k, v in table.items()}

    hot = merge_spans([
        {"start": it["review"]["start"], "end": it["review"]["end"], "items": [it["id"]]}
        for it in items if it["correct_rate"] < HOT
    ])
    summary = {
        "title": quiz["title"], "type": quiz["type"], "respondents": n,
        "average_rate": rate(sum(r["correct"] for r in results), sum(r["total"] for r in results)),
        "all_correct_share": rate(sum(it["correct_rate"] == 1 for it in items), len(items)),
        "by_checks": pooled("by_checks"), "by_section": pooled("by_section"),
        "items": items, "hot_spans": hot,
    }
    if quiz["type"] != "meeting":  # 회의는 개인별 표를 만들지 않는다 — 성적이 아니라 인식 차이의 지도다
        summary["people"] = [
            {"respondent": r["respondent"], "correct": r["correct"], "total": r["total"],
             "review": [sp["label"] for sp in r["review_spans"]]} for r in ranked
        ]
    return summary


def insights_html(text):
    """insights.md의 아주 작은 마크다운(제목, 불릿, 굵게, 코드) → HTML."""
    out, in_list = [], False
    for line in text.splitlines():
        s = html.escape(line.strip())
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        bullet = re.match(r"^[-*]\s+(.*)", s)
        if bullet:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{bullet.group(1)}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if s.startswith("#"):
            out.append(f"<h2>{s.lstrip('# ')}</h2>")
        elif s:
            out.append(f"<p>{s}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def main():
    work = Path(sys.argv[1])
    quiz, results = grade_all(work)
    summary = summarize(quiz, results)
    (work / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    notes = work / "insights.md"
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("{{title}}", html.escape(summary["title"]))
    page = page.replace("{{insights}}", insights_html(notes.read_text(encoding="utf-8")) if notes.exists() else "")
    page = page.replace("{{summary_json}}", json.dumps(summary, ensure_ascii=False).replace("</", "<\\/"))
    (work / "summary.html").write_text(page, encoding="utf-8")

    print(f"응답 {summary['respondents']}명 · 평균 정답률 {summary['average_rate']:.0%}")
    for it in summary["items"]:
        if it["flags"]:
            tw = it["top_wrong"]
            print(f" - {it['id']} {it['correct_rate']:.0%} {it['flags']} 가장 많이 고른 오답: \"{tw['text']}\" ({tw['count']}명)")
    print(work / "summary.json")
    print(work / "summary.html", "" if notes.exists() else "(insights.md가 아직 없어 발견 섹션은 비어 있음)")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
