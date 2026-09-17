"""테스트용 가상 응답을 만든다. evals/files/<샘플>/quiz.json을 읽어 answers/*.json을 쓴다.

사용: python build_answers.py
각 응답은 "문항 → 고른 보기 글의 일부"로 적는다. 적지 않은 문항은 정답을 고른 것으로 친다.
일부러 넣어 둔 패턴은 각 샘플 위의 주석 참고.
"""
import json
from pathlib import Path

FILES = Path(__file__).resolve().parent / "files"

# ── 강의 (7명) ───────────────────────────────────────────────────────
# ① q4 no-cache: 7명 중 5명이 "디스크에 아예 저장하지 않습니다"(= no-store의 설명)를 고름 → 같은 오해 공유, 오답 > 정답
# ② q5·q10: 같은 혼동의 여파로 no-cache/no-store를 뒤바꿔 고른 사람들
# ③ q8: 틀린 4명이 오답 세 개에 흩어짐 → 찍은 흔적
# ④ q6: 점수 높은 사람들이 틀리고 낮은 사람들이 맞힘 → 문항 문제 신호
# ⑤ 오세린은 혼자 많이 틀림 → 개인 조치  ⑥ 이해 문항 정답률 ≪ 기억 문항
LECTURE = {
    "김하늘": {"q4": "아예 저장하지", "q6": "새로 보낼 때마다"},
    "이도윤": {"q4": "아예 저장하지", "q6": "기간이 끝날 때", "q8": "같은 본문을 다시"},
    "박서연": {"q6": "새로 보낼 때마다", "q10": "`no-store`"},
    "최민재": {"q4": "아예 저장하지", "q5": "`no-cache`", "q8": "함께 본문을 보냅니다"},
    "정유나": {"q4": "아예 저장하지", "q5": "`no-cache`", "q10": "`no-store`", "q8": "새 `ETag`만"},
    "한지호": {"q3": "확인한 뒤", "q5": "`no-cache`", "q9": "거의 바뀌지"},
    "오세린": {"q1": "압축", "q2": "기본값", "q3": "새로 받아", "q4": "아예 저장하지", "q7": "`Cache-Control`",
               "q8": "같은 본문을 다시", "q9": "저장본이 지워지기", "q10": "`no-store`"},
}

# ── 회의 (5명) ───────────────────────────────────────────────────────
# ① q5 스토어 심사 확인: 5명 중 3명이 "지현 님이 맡기로"라고 알고 있음 → 담당 없는 일을 누가 하는 줄 아는 상태
# ② q1 출시일: 2명이 기각된 10월 21일로 알고 있음
# ③ q6 푸시 알림: 1명이 "빼기로 했다"로 알고 있음
MEETING = {
    "강다은": {"q5": "지현 님이"},
    "윤재현": {"q1": "10월 21일", "q5": "지현 님이"},
    "서지우": {},
    "문태양": {"q1": "10월 21일", "q5": "지현 님이", "q6": "빼기로"},
    "임소율": {"q3": "이번 주 금요일"},
}


def build(sample, people):
    folder = FILES / sample
    quiz = {q["id"]: q for q in json.loads((folder / "quiz.json").read_text(encoding="utf-8"))["items"]}
    out = folder / "answers"
    out.mkdir(exist_ok=True)
    for n, (name, picks) in enumerate(people.items()):
        answers = {}
        for qid, q in quiz.items():
            if qid in picks:
                match = [c["id"] for c in q["choices"] if picks[qid] in c["text"] and c["id"] != q["answer"]]
                assert len(match) == 1, f"{sample} {name} {qid}: '{picks[qid]}'에 맞는 오답 보기가 {len(match)}개"
                answers[qid] = match[0]
            else:
                answers[qid] = q["answer"]
        (out / f"{n + 1:02d}.json").write_text(
            json.dumps({"respondent": name, "submitted_at": f"2026-09-17T1{n}:05:00", "answers": answers}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    print(sample, len(people), "명")


if __name__ == "__main__":
    build("lecture-http-caching", LECTURE)
    build("meeting-beta-schedule", MEETING)
