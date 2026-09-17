"""키프레임 이미지 → screens.json (Gemini가 이미지를 직접 본다)

사용: GEMINI_API_KEY=... python engine/screens.py <작업 폴더>
      작업 폴더에는 frames.json 과 frames/ 가 있어야 한다 (video-ingest의 결과).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import Gemini  # noqa: E402
from pipeline import prompt, run_script  # noqa: E402

BATCH = 8  # 한 번의 호출에 보내는 프레임 수. 너무 많으면 프레임 사이에 내용이 섞이고, 너무 적으면 호출 한도를 빨리 쓴다.


def read_batch(llm, work, frames, first_number, note=""):
    parts = [f"프레임 {len(frames)}장을 보낸다. 번호는 {first_number:04d}부터다.{note}"]
    for i, fr in enumerate(frames):
        parts += [f"프레임 {first_number + i:04d}:", work / fr["image"]]
    return llm.generate(prompt("screens.md"), parts, "screens")


def run(work, llm):
    """키프레임을 읽혀 screens.json을 만든다. 성공하면 True."""
    work = Path(work)
    frames = json.loads((work / "frames.json").read_text(encoding="utf-8"))
    if frames:
        chunks = []
        for start in range(0, len(frames), BATCH):
            note = "" if start == 0 else " 첫 프레임이 직전 묶음의 마지막 프레임과 같은지는 알 수 없으므로, 이 묶음의 첫 프레임은 '같음'으로 쓰지 말고 내용을 적는다."
            chunks.append(read_batch(llm, work, frames[start:start + BATCH], start + 1, note))
        (work / "screens-draft.md").write_text("\n\n".join(chunks) + "\n", encoding="utf-8")

    # 검증: 빠뜨린 프레임, 없는 종류 등. 오류가 나면 그 프레임들만 한 번 더 읽힌다.
    code, out = run_script("screen-read/scripts/build_screens.py", work)
    if code:
        bad = sorted({int(n) for n in re.findall(r"^ - (\d{4}):", out, re.M)})
        print(f"  [screens] 오류 {len(bad)}건 — 해당 프레임을 다시 읽습니다: {bad}")
        draft = (work / "screens-draft.md").read_text(encoding="utf-8")
        for n in bad:
            if 1 <= n <= len(frames):
                redo = read_batch(llm, work, [frames[n - 1]], n, " 이 프레임은 '같음'으로 쓰지 말고 내용을 적는다.")
                draft = re.sub(rf"^## {n:04d} \|.*?(?=^## \d{{4}} \||\Z)", "", draft, flags=re.S | re.M) + "\n\n" + redo + "\n"
        blocks = sorted(re.findall(r"^## \d{4} \|.*?(?=^## \d{4} \||\Z)", draft, flags=re.S | re.M))
        (work / "screens-draft.md").write_text("\n".join(b.strip() + "\n" for b in blocks), encoding="utf-8")
        code, out = run_script("screen-read/scripts/build_screens.py", work)
    print("  [screens]", out.splitlines()[-1] if out else "")
    return code == 0


def main():
    llm = Gemini()
    ok = run(sys.argv[1], llm)
    t = llm.totals()
    print(f"호출 {t['calls']}회 · 입력 {t['in']:,} + 출력 {t['out']:,} + 사고 {t['thinking']:,} 토큰 · {t['sec']:.0f}초 · 모델 {', '.join(t['models'])}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        _s.reconfigure(encoding="utf-8")
    main()
