"""전사 + 화면 → 리포트 → 퀴즈 → 만화. 에이전트 없이 코드가 단계별로 모델을 호출한다.

지식은 skills/의 문서를, 검증·렌더링은 skills/의 스크립트를 그대로 쓴다. 이 파일이 맡는 것은 "진행"뿐이다:
무엇을 어떤 순서로 부르고, 검증이 지적한 것을 어떻게 되돌려 고치게 하는가.

사용: GEMINI_API_KEY=... python engine/pipeline.py <작업 폴더> [--type meeting|education|general] [--only report|quiz|comic]
      작업 폴더에는 transcript.json 과/또는 screens.json 이 있어야 한다.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import Gemini, LLMError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKILLS, PROMPTS = ROOT / "skills", ROOT / "engine" / "prompts"
TYPES = ("meeting", "education", "general")
MAX_FIXES = 2        # 검증 오류를 되돌려 고치게 하는 횟수
CLASSIFY_CHARS = 6000


def doc(*parts):
    return SKILLS.joinpath(*parts).read_text(encoding="utf-8")


def prompt(name):
    return (PROMPTS / name).read_text(encoding="utf-8")


def run_script(path, work):
    r = subprocess.run([sys.executable, str(SKILLS / path), str(work)], capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return r.returncode, (r.stdout + r.stderr).strip()


def write_checked(llm, stage, system, user, draft, checker, work, first=None):
    """초안을 쓰게 하고(또는 받은 초안으로 시작하고), 검증 스크립트가 지적한 오류·경고를 되돌려 고치게 한다.
    오류가 끝내 남으면 False. 경고만 남은 것은 통과로 본다(한 번은 고칠 기회를 준다)."""
    text = first if first is not None else llm.generate(system, user, stage)
    for n in range(MAX_FIXES + 1):
        (work / draft).write_text(text + "\n", encoding="utf-8")
        code, out = run_script(checker, work)
        warned = "경고:" in out
        print(f"  [{stage}] 시도 {n + 1}: {'오류' if code else ('경고' if warned else '통과')} — {out.splitlines()[0] if out else ''}")
        if (code == 0 and not warned) or n == MAX_FIXES or (code == 0 and n >= 1):
            return code == 0, out
        text = llm.generate(system, f"{user}\n\n---\n아래는 네가 쓴 {draft}와 검사 결과다. 지적된 부분을 고쳐서 {draft} 전체를 다시 출력하라. "
                                    f"지적되지 않은 부분은 바꾸지 마라.\n\n## 네가 쓴 {draft}\n{text}\n\n## 검사 결과\n{out}", f"{stage}-fix")


def target_items(work):
    """영상 길이 → 본문 항목 수의 기준 범위 (근거 규칙의 '분량 감각'과 같은 기준)."""
    duration = 0
    for name in ("info.json", "transcript.json"):
        if (work / name).exists():
            duration = json.loads((work / name).read_text(encoding="utf-8")).get("duration") or duration
    minutes = max(duration / 60, 1)
    if minutes <= 10:
        lo, hi = 4 * minutes, 6 * minutes
    elif minutes <= 30:
        lo, hi = 40 + (minutes - 10) * 0.5, 60 + (minutes - 10) * 1.0
    else:
        lo, hi = 50 + (minutes - 30) * 1.0, 80 + (minutes - 30) * 1.3
    return int(lo), int(hi)


def make_report(llm, work, kind):
    code, out = run_script("integrated-report/scripts/merge_timeline.py", work)
    if code:
        sys.exit(out)
    timeline = (work / "timeline.md").read_text(encoding="utf-8")

    if kind is None:
        answer = llm.generate(prompt("classify.md"), timeline[:CLASSIFY_CHARS], "classify", temperature=0, max_output=2000).strip().lower()
        kind = next((t for t in TYPES if t in answer), "general")
    print(f"  유형: {kind}")

    system = "\n\n".join([prompt("report.md"), "# 근거 규칙\n\n" + doc("integrated-report", "references", "evidence-rules.md"),
                          "# 형식 가이드\n\n" + doc("integrated-report", "references", f"{kind}-report.md")])
    lo, hi = target_items(work)
    size = f"본문 항목 수의 기준은 약 {lo}~{hi}개다 (영상 길이에서 계산. 내용이 실제로 있는 만큼만 — 지어내서 채우지 않는다)."
    user = f"영상 유형: {kind} (frontmatter의 type에 그대로 쓴다)\n{size}\n\n# timeline.md\n\n{timeline}"
    ok, _ = write_checked(llm, "report", system, user, "draft.md", "integrated-report/scripts/check_report.py", work)

    # 검토: 항목마다 원문을 나란히 놓은 대조표(evidence.md)를 주고 한 번 더 보게 한다. 에이전트가 스스로 하던 일.
    if ok:
        draft, evidence = (work / "draft.md").read_text(encoding="utf-8"), (work / "evidence.md").read_text(encoding="utf-8")
        reviewed = llm.generate(prompt("review.md") + "\n\n# 근거 규칙\n\n" + doc("integrated-report", "references", "evidence-rules.md"),
                                f"{size}\n\n# draft.md\n\n{draft}\n\n# 근거 대조표\n\n{evidence}\n\n# timeline.md (빠진 대목을 찾을 때 쓴다)\n\n{timeline}", "review")
        ok2, _ = write_checked(llm, "review", system, user, "draft.md", "integrated-report/scripts/check_report.py", work, first=reviewed)
        if not ok2:  # 검토가 형식을 깨뜨렸으면 검토 전 것으로 되돌린다
            (work / "draft.md").write_text(draft, encoding="utf-8")
            print("  [review] 검토본이 검증을 통과하지 못해 검토 전 초안을 씁니다.")
    code, out = run_script("integrated-report/scripts/check_report.py", work)
    if code:
        sys.exit("리포트가 검증을 통과하지 못했습니다:\n" + out)
    code, out = run_script("integrated-report/scripts/render.py", work)
    if code:
        sys.exit("렌더링 실패: " + out)


def report_text(work):
    return json.dumps(json.loads((work / "report.json").read_text(encoding="utf-8")), ensure_ascii=False, indent=1)


def make_quiz(llm, work):
    kind = json.loads((work / "report.json").read_text(encoding="utf-8"))["type"]
    system = "\n\n".join([prompt("quiz.md"), "# 문항 쓰는 법\n\n" + doc("comprehension-quiz", "references", "item-writing.md"),
                          "# 영상 유형별 가이드\n\n" + doc("comprehension-quiz", "references", f"{kind}-quiz.md")])
    ok, out = write_checked(llm, "quiz", system, "# report.json\n\n" + report_text(work), "quiz-draft.md",
                            "comprehension-quiz/scripts/build_quiz.py", work)
    return ok


def make_comic(llm, work):
    screens = ""
    if (work / "screens.json").exists():
        rows = json.loads((work / "screens.json").read_text(encoding="utf-8"))["screens"]
        usable = [s for s in rows if s.get("kind") not in ("people", "participants")]
        screens = "\n\n# 배경으로 쓸 수 있는 영상 화면\n" + ("\n".join(
            f"- {int(s['time']) // 60:02d}:{int(s['time']) % 60:02d} · {s['kind']} · {(s.get('text') or s.get('description') or '').splitlines()[0][:60]}"
            for s in usable) or "(없음 — 모든 컷을 '사무실'이나 '없음'으로 한다)")
    system = "\n\n".join([prompt("comic.md"), "# 스토리보드 짜는 법\n\n" + doc("comic-recap", "references", "storyboard.md"),
                          "# 캐릭터와 표정\n\n" + doc("comic-recap", "references", "cast.md")])
    ok, out = write_checked(llm, "comic", system, "# report.json\n\n" + report_text(work) + screens, "comic-draft.md",
                            "comic-recap/scripts/build_comic.py", work)
    return ok


def run(work, llm, kind=None, only=None, on_stage=None):
    """리포트 → 퀴즈 → 만화 → 모아보기. 실패한 단계의 이름 목록을 돌려준다(리포트 실패는 SystemExit).
    on_stage(name)이 주어지면 각 단계에 들어갈 때 불러 준다 — 백엔드가 진행 상태를 알리는 데 쓴다."""
    work, failed = Path(work), []
    tell = on_stage or (lambda name: print(name))
    if only in (None, "report"):
        tell("report")
        make_report(llm, work, kind)
    if only in (None, "quiz"):
        tell("quiz")
        make_quiz(llm, work) or failed.append("quiz")
    if only in (None, "comic"):
        tell("comic")
        make_comic(llm, work) or failed.append("comic")
    run_script("video-report-pipeline/scripts/make_index.py", work)
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--type", choices=TYPES, help="영상 유형을 직접 지정 (없으면 모델이 판별)")
    ap.add_argument("--only", choices=("report", "quiz", "comic"))
    ap.add_argument("--models", help="시도할 모델을 쉼표로 (앞의 것부터)")
    args = ap.parse_args()
    work = Path(args.work)
    llm = Gemini(args.models.split(",") if args.models else None)

    failed = []
    try:
        failed = run(work, llm, args.type, args.only)
    except LLMError as e:
        failed.append(f"중단: {e}")
    finally:
        t = llm.totals()
        (work / "usage.json").write_text(json.dumps({"total": t, "calls": llm.usage, "skipped_models": llm.skipped, "failed": failed},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n호출 {t['calls']}회 · 입력 {t['in']:,} + 출력 {t['out']:,} + 사고 {t['thinking']:,} 토큰 · {t['sec']:.0f}초 · 모델 {', '.join(t['models'])}")
        if llm.skipped:
            print("응답하지 않은 모델: " + ", ".join(f"{m} ({why})" for m, why in llm.skipped.items()))
        if failed:
            print("실패: " + ", ".join(failed))
            sys.exit(1)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        _s.reconfigure(encoding="utf-8")
    main()
