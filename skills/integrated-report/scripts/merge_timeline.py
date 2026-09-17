"""transcript.json + screens.json → timeline.md

"이 화면이 떠 있는 동안 이런 말을 했다"를 시간순으로 묶는다.
사용: python merge_timeline.py <작업 폴더>
"""
import sys
from pathlib import Path

from common import load_inputs, to_ts

CHUNK = 60  # 화면 정보가 없을 때 발화를 끊는 단위(초)
LOW_CONFIDENCE = 0.5


def blocks_from(screens, duration):
    if not screens:
        n = int(duration // CHUNK) + 1
        return [(i * CHUNK, min((i + 1) * CHUNK, duration), None) for i in range(n)]
    out = []
    if screens[0]["time"] > 0:
        out.append((0, screens[0]["time"], None))
    for i, sc in enumerate(screens):
        end = screens[i + 1]["time"] if i + 1 < len(screens) else duration
        out.append((sc["time"], max(end, sc["time"]), sc))
    return out


def main():
    work = Path(sys.argv[1])
    segments, screens, duration = load_inputs(work)
    # 화면이 전부 사람·참가자 타일이면 화면 기준으로 묶는 의미가 없다(발언자에 따라 계속 바뀐다) → 시간 기준으로 묶는다
    tiles_only = bool(screens) and all(s.get("kind") in ("people", "participants") for s in screens)
    if tiles_only:
        screens = []

    lines = [
        "# 타임라인",
        "",
        f"길이 {to_ts(duration)} · 발화 {len(segments)}개 · 화면 {len(screens)}개",
        "`(?)`가 붙은 발화는 전사 신뢰도가 낮은 구간이다.",
        *(["화면에는 참가자 타일(사람, 이름표)만 나왔다. 공유된 자료는 없다."] if tiles_only else []),
        "",
    ]
    number = 0
    for start, end, sc in blocks_from(screens, duration):
        said = [s for s in segments if start <= s["start"] < end or (end == duration and s["start"] >= end)]
        if sc is None and not said:
            continue
        head = f"## [{to_ts(start)}–{to_ts(end)}]"
        if sc:
            number += 1
            head += f" 화면 {number} · {sc.get('kind', 'other')}"
        lines += [head, ""]
        if sc:
            if sc.get("text"):
                lines += ["**화면 글자:**", "", "```", sc["text"].strip(), "```", ""]
            if sc.get("description"):
                lines += [f"**화면 설명:** {sc['description'].strip()}", ""]
        for s in said:
            who = f"{s['speaker']}: " if s.get("speaker") else ""
            flag = " (?)" if s.get("confidence", 1) < LOW_CONFIDENCE else ""
            lines.append(f"- [{to_ts(s['start'])}] {who}{s['text'].strip()}{flag}")
        if not said:
            lines.append("_(이 화면 동안 발화 없음)_")
        lines.append("")

    out = work / "timeline.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{out} ({len(lines)}줄)")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
