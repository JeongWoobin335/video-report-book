"""audio.wav → transcript.json (faster-whisper)

사용: python transcribe.py <작업 폴더> [--language ko] [--model large-v3-turbo] [--terms "a, b"] [--vad-off]
필요: pip install faster-whisper
"""
import argparse
import json
import math
import sys
from pathlib import Path

LOW = 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--language", default=None, help="ko, en … 주지 않으면 자동 감지")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--terms", default="", help="영상에 나오는 용어·고유명사 (쉼표로 구분)")
    ap.add_argument("--vad-off", action="store_true", help="무음 구간 건너뛰기를 끈다")
    args = ap.parse_args()

    work = Path(args.work)
    audio = work / "audio.wav"
    info = json.loads((work / "info.json").read_text(encoding="utf-8")) if (work / "info.json").exists() else {}
    if not audio.exists():
        if info.get("has_audio") is False:
            (work / "transcript.json").write_text(json.dumps(
                {"language": None, "duration": info.get("duration", 0), "engine": None, "segments": []}, ensure_ascii=False), encoding="utf-8")
            print("오디오 트랙이 없는 영상입니다. 빈 전사를 썼습니다.")
            return
        sys.exit(f"{audio} 가 없습니다. video-ingest를 먼저 실행하세요.")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper가 없습니다: pip install faster-whisper")

    try:
        model = WhisperModel(args.model, device="cuda", compute_type="float16")
        device = "GPU"
    except Exception:  # GPU나 CUDA 라이브러리가 없으면 CPU로
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        device = "CPU"

    terms = ", ".join(t.strip() for t in args.terms.split(",") if t.strip())
    found, meta = model.transcribe(
        str(audio), language=args.language, vad_filter=not args.vad_off,
        initial_prompt=(f"용어: {terms}." if terms else None),
        condition_on_previous_text=False,  # 앞 문장에 끌려 같은 말을 반복하는 현상을 줄인다
    )
    segments = []
    for s in found:
        text = s.text.strip()
        if text:
            segments.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text, "speaker": None,
                             "confidence": round(min(1.0, math.exp(s.avg_logprob)), 2)})

    first = work / "transcript.json"
    if terms and first.exists() and not (work / "transcript.first.json").exists():
        first.replace(work / "transcript.first.json")  # 용어를 넣어 다시 돌릴 때, 비교할 수 있게 첫 결과를 남겨 둔다
    out = {"language": meta.language, "duration": round(meta.duration, 2), "engine": f"faster-whisper {args.model}", "terms": terms, "segments": segments}
    (work / "transcript.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    low = [s for s in segments if s["confidence"] < LOW]
    # 짧은 인사("안녕하세요")가 연달아 나오는 것은 정상이다. 어느 정도 긴 문장이 되풀이될 때만 헛도는 것으로 본다.
    repeats = sum(1 for a, b in zip(segments, segments[1:]) if a["text"] == b["text"] and len(a["text"]) >= 12)
    print(f"{work / 'transcript.json'}")
    print(f"언어 {meta.language} ({meta.language_probability:.0%}) · {device} · 발화 {len(segments)}개 · 신뢰도 낮은 구간 {len(low)}개"
          + (f" · 같은 문장 연속 반복 {repeats}회 — 확인 필요" if repeats >= 2 else ""))
    for s in low[:5]:
        print(f"  (?) [{int(s['start']) // 60:02d}:{int(s['start']) % 60:02d}] {s['text'][:50]}")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
