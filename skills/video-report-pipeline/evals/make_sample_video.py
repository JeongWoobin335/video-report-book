"""테스트용 강의 영상을 만든다: 슬라이드 이미지 + 한국어 TTS 음성 → samples/lecture-http-caching.mp4

사용: python make_sample_video.py        (Windows 전용 — 음성 합성에 System.Speech를 쓴다)
대본과 슬라이드는 integrated-report/evals/build_samples.py의 강의 샘플을 그대로 쓴다.
"""
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills" / "integrated-report" / "evals"))
from build_samples import LECTURE, LECTURE_SCREENS, t  # noqa: E402

OUT = ROOT / "samples" / "lecture-http-caching.mp4"
FONT = "C:/Windows/Fonts/malgunbd.ttf"
GAP = 0.5  # 문장 사이 쉬는 시간(초)


def make_slide(text, path):
    img = Image.new("RGB", (1280, 720), "#fdfcf8")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 14], fill="#2f5fd0")
    lines = text.split("\n")
    y = 70
    for i, line in enumerate(lines):
        size = 54 if i == 0 else 34
        mono = line.startswith(("Cache-Control", "app.", "index.")) or "max-age=" in line and i > 0
        font = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf" if mono and line.isascii() else FONT, size)
        d.text((90, y), line, font=font, fill="#1d3a8a" if i == 0 else "#1f2328")
        y += size + (34 if i == 0 else 18)
    img.save(path)


def speak_all(lines, folder):
    """PowerShell 한 번으로 모든 문장을 wav로 합성한다."""
    (folder / "lines.json").write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    ps = f"""
Add-Type -AssemblyName System.Speech
$lines = Get-Content -Raw -Encoding UTF8 '{folder / "lines.json"}' | ConvertFrom-Json
$i = 0
foreach ($line in $lines) {{
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice('Microsoft Heami Desktop'); $s.Rate = 1
  $s.SetOutputToWaveFile(('{folder}\\{{0:d3}}.wav' -f $i)); $s.Speak($line); $s.Dispose(); $i++
}}"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def main():
    OUT.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        speak_all([line[2] for line in LECTURE], tmp)

        # 문장별 길이 → 영상에서의 실제 시작 시각
        starts, now = [], 1.0
        for i in range(len(LECTURE)):
            with wave.open(str(tmp / f"{i:03d}.wav")) as w:
                dur = w.getnframes() / w.getframerate()
            starts.append(now)
            now += dur + GAP
        total = now + 1.0

        # 슬라이드는 원래 대본에서 그 슬라이드가 뜬 직후의 문장이 시작될 때 바뀐다
        cuts = []
        for n, sc in enumerate(LECTURE_SCREENS):
            first = next(i for i, line in enumerate(LECTURE) if t(line[0]) >= t(sc["time"]))
            make_slide(sc["text"], tmp / f"slide{n}.png")
            cuts.append(0.0 if n == 0 else max(starts[first] - 0.8, 0))
        with open(tmp / "slides.txt", "w", encoding="utf-8") as f:
            for n, start in enumerate(cuts):
                end = cuts[n + 1] if n + 1 < len(cuts) else total
                f.write(f"file 'slide{n}.png'\nduration {end - start:.2f}\n")
            f.write(f"file 'slide{len(cuts) - 1}.png'\n")

        # 오디오: 문장들을 제 시각에 놓고 섞는다
        inputs, filters = [], []
        for i, s in enumerate(starts):
            inputs += ["-i", str(tmp / f"{i:03d}.wav")]
            filters.append(f"[{i}:a]adelay={int(s * 1000)}:all=1[a{i}]")
        mix = "".join(f"[a{i}]" for i in range(len(starts)))
        filters.append(f"{mix}amix=inputs={len(starts)}:normalize=0,apad=whole_dur={total:.2f}[out]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
                        "-map", "[out]", "-ar", "44100", str(tmp / "voice.wav")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "slides.txt"),
                        "-i", str(tmp / "voice.wav"), "-vf", "fps=10,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                        "-c:a", "aac", "-b:a", "96k", "-t", f"{total:.2f}", str(OUT)], check=True)
    print(f"{OUT} ({total / 60:.1f}분, 슬라이드 {len(LECTURE_SCREENS)}장, 문장 {len(LECTURE)}개)")


if __name__ == "__main__":
    main()
