"""영상 → 작업 폴더(video, info.json, audio.wav, frames/, frames.json)

사용: python ingest.py <영상 파일> [--work 폴더] [--max-frames 40] [--threshold 10] [--every 2] [--frames-only]
필요: ffmpeg, ffprobe (PATH), Pillow
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"실패: {' '.join(map(str, cmd[:3]))} …\n{r.stderr[-800:]}")
    return r.stdout


def probe(video: Path):
    data = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)]))
    v = next((s for s in data["streams"] if s["codec_type"] == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {
        "source": video.name,
        "duration": round(float(data["format"]["duration"]), 2),
        "has_video": v is not None, "has_audio": a is not None,
        "width": v and v.get("width"), "height": v and v.get("height"),
    }


def dhash(path: Path, size=16):
    """그림의 대략적인 모양을 나타내는 비트열. 두 해시에서 다른 비트의 수가 그림의 차이다."""
    img = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = img.tobytes()  # L 모드라 바이트 하나가 픽셀 하나
    return [px[r * (size + 1) + c] > px[r * (size + 1) + c + 1] for r in range(size) for c in range(size)]


def pick_keyframes(video: Path, duration: float, every: float, threshold: int, max_frames: int):
    """일정 간격으로 작게 훑어 보고, 직전 채택 프레임과 충분히 달라진 시각만 고른다. → [(시각, 직전과의 차이)]"""
    with tempfile.TemporaryDirectory() as tmp:
        run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=1/{every},scale=320:-2", "-q:v", "5", f"{tmp}/%06d.jpg"])
        picked, last = [], None
        for i, f in enumerate(sorted(Path(tmp).glob("*.jpg"))):
            h = dhash(f)
            diff = 256 if last is None else sum(a != b for a, b in zip(h, last))
            if diff >= threshold:
                picked.append((min(i * every, max(duration - 0.1, 0)), diff))
                last = h
    while len(picked) > max_frames:  # 상한을 넘으면 변화가 가장 작았던 것부터 버린다 (첫 장은 남긴다)
        picked.remove(min(picked[1:], key=lambda x: x[1]))
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--work")
    ap.add_argument("--max-frames", type=int, default=40)
    ap.add_argument("--threshold", type=int, default=10, help="직전 채택 프레임과 이만큼(256비트 중) 달라야 새 키프레임으로 친다")
    ap.add_argument("--every", type=float, default=2.0, help="몇 초마다 훑어볼지")
    ap.add_argument("--frames-only", action="store_true", help="키프레임만 다시 뽑는다 (audio.wav는 건드리지 않는다)")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool}을 찾을 수 없습니다. ffmpeg를 설치하고 PATH에 추가하세요.")
    src = Path(args.video)
    if not src.exists():
        sys.exit(f"{src} 가 없습니다.")
    work = Path(args.work) if args.work else Path("work") / src.stem
    work.mkdir(parents=True, exist_ok=True)

    info = probe(src)
    video = work / f"video{src.suffix.lower()}"
    if src.resolve() != video.resolve():
        shutil.copy2(src, video)
    (work / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    if info["has_audio"] and not args.frames_only:
        run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(work / "audio.wav")])

    frames_dir = work / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames = []
    if info["has_video"]:
        frames_dir.mkdir()
        picked = pick_keyframes(video, info["duration"], args.every, args.threshold, args.max_frames)
        for n, (t, _) in enumerate(picked, 1):
            name = f"frames/{n:04d}.jpg"
            # 화면이 막 바뀌는 중일 수 있으므로 살짝 뒤의 프레임을 뽑는다. 읽기 좋은 크기로 줄인다.
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(min(t + 0.7, max(info["duration"] - 0.1, 0))), "-i", str(video),
                 "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "3", str(work / name)])
            frames.append({"time": round(t, 1), "image": name})
    (work / "frames.json").write_text(json.dumps(frames, ensure_ascii=False, indent=1), encoding="utf-8")

    m, s = divmod(int(info["duration"]), 60)
    print(f"{work}")
    print(f"길이 {m}분 {s}초 · 오디오 {'있음' if info['has_audio'] else '없음'} · 키프레임 {len(frames)}장"
          + (f" (상한 {args.max_frames}에 걸림 — SKILL.md의 '키프레임을 고르는 방식' 참고)" if len(frames) >= args.max_frames else ""))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
