"""audio.wav → transcript.json (Gemini가 오디오를 직접 듣는다 — GPU가 필요 없다)

사용: GEMINI_API_KEY=... python engine/transcribe.py <작업 폴더> [--language ko] [--chunk-min 8]
긴 오디오는 작은 파일로 나눠 보낸다(요청 크기 제한). 조각마다 시각은 조각의 처음이 0이므로 합칠 때 보정한다.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import Gemini  # noqa: E402
from pipeline import prompt  # noqa: E402

LINE = re.compile(r"^\[(\d+):(\d{2}(?:\.\d+)?)\s*[-–~]\s*(\d+):(\d{2}(?:\.\d+)?)\]\s*(.+)$")
# 전사 전용 모델(gemini-3.5-transcribe)은 시험에서 빈 응답을 돌려줬고 분당 토큰 한도도 1만으로 작다 → 일반 모델을 쓴다.


def find_audio(work):
    """작업 폴더의 오디오. video-ingest가 만든 audio.wav, 또는 브라우저가 뽑아 올린 audio.(mp3|m4a|ogg|webm|wav)."""
    return next((p for p in sorted(Path(work).glob("audio.*")) if p.suffix.lower() in {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".aac"}), None)


def run(work, llm, language="ko", chunk_min=8):
    """오디오를 받아적어 transcript.json을 쓴다. 돌려주는 값: 시각이 이상한 줄의 수."""
    work = Path(work)
    info = json.loads((work / "info.json").read_text(encoding="utf-8"))
    audio = find_audio(work)
    if not info.get("has_audio") or audio is None:
        (work / "transcript.json").write_text(json.dumps({"language": None, "duration": info["duration"], "engine": None, "segments": []}), encoding="utf-8")
        print("  [transcribe] 오디오가 없습니다. 빈 전사를 썼습니다.")
        return 0

    segments, step, before = [], chunk_min * 60, len(llm.usage)
    with tempfile.TemporaryDirectory() as tmp:
        # 16kHz 모노 mp3로 줄여서 자른다 (8분 ≈ 2MB)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
                        "-f", "segment", "-segment_time", str(step), f"{tmp}/part%03d.mp3"], check=True)
        for n, part in enumerate(sorted(Path(tmp).glob("part*.mp3"))):
            offset = n * step
            text = llm.generate(prompt("transcribe.md"), [f"언어: {language}. 이 오디오를 받아적어라.", part], "transcribe", temperature=0, max_output=32000)
            got = 0
            for line in text.splitlines():
                m = LINE.match(line.strip())
                if not m:
                    continue
                start = int(m.group(1)) * 60 + float(m.group(2)) + offset
                end = int(m.group(3)) * 60 + float(m.group(4)) + offset
                said = m.group(5).strip()
                seg = {"start": round(start, 2), "end": round(max(end, start), 2), "text": re.sub(r"\s*\(\?\)\s*$", "", said), "speaker": None}
                if said.endswith("(?)"):
                    seg["confidence"] = 0.3  # 모델이 스스로 불확실하다고 표시한 줄
                segments.append(seg)
                got += 1
            print(f"  [transcribe] 조각 {n + 1}: {got}줄 ({llm.usage[-1]['model']}, {llm.usage[-1]['sec']}초)")

    # 시각이 영상 길이를 넘거나 뒤로 가는 줄은 모델이 시각을 지어낸 것이다 → 알려준다
    bad = [s for s in segments if s["start"] > info["duration"] + 2] + [b for a, b in zip(segments, segments[1:]) if b["start"] + 1 < a["start"]]
    out = {"language": language, "duration": info["duration"], "engine": "gemini " + "/".join(sorted({u["model"] for u in llm.usage[before:]})),
           "terms": "", "segments": segments}
    (work / "transcript.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  [transcribe] 발화 {len(segments)}개" + (f" · 시각이 이상한 줄 {len(bad)}개 — 확인 필요" if bad else ""))
    return len(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--chunk-min", type=float, default=8, help="한 번에 보낼 오디오 길이(분)")
    args = ap.parse_args()
    llm = Gemini()
    run(args.work, llm, args.language, args.chunk_min)
    t = llm.totals()
    print(f"호출 {t['calls']}회 · 입력 {t['in']:,} + 출력 {t['out']:,} + 사고 {t['thinking']:,} 토큰 · {t['sec']:.0f}초")
    if llm.skipped:
        print("응답하지 않은 모델: " + ", ".join(f"{m} ({why})" for m, why in llm.skipped.items()))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        _s.reconfigure(encoding="utf-8")
    main()
