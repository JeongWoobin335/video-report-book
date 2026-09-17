"""screens-draft.md + frames.json → screens.json

사용: python build_screens.py <작업 폴더>
"""
import json
import re
import sys
from pathlib import Path

KINDS = {"slide", "screen_share", "whiteboard", "demo", "people", "participants", "other"}


def main():
    work = Path(sys.argv[1])
    frames = json.loads((work / "frames.json").read_text(encoding="utf-8"))
    if not frames:
        (work / "screens.json").write_text('{"screens": []}', encoding="utf-8")
        print("프레임이 없습니다. 빈 screens.json을 썼습니다.")
        return
    draft = work / "screens-draft.md"
    if not draft.exists():
        sys.exit(f"{draft} 가 없습니다.")

    # "## 0001 | slide" 단위로 나눠 글자/설명을 모은다
    entries, cur, field = {}, None, None
    for raw in draft.read_text(encoding="utf-8").splitlines():
        if h := re.match(r"^##\s*(\d+)\s*\|\s*(.+?)\s*$", raw):
            cur = {"head": h.group(2), "text": [], "description": []}
            entries[int(h.group(1))] = cur
            field = None
        elif cur is None:
            continue
        elif raw.startswith("글자:"):
            field = "text"
            if rest := raw[3:].strip():
                cur["text"].append(rest)
        elif raw.startswith("설명:"):
            field = "description"
            cur["description"].append(raw[3:].strip())
        elif field:
            cur[field].append(raw.rstrip() if field == "text" else raw.strip())

    errors, screens = [], []
    for n, fr in enumerate(frames, 1):
        e = entries.get(n)
        if e is None:
            errors.append(f"{n:04d}: 초안에 없습니다 ({fr['image']}).")
            continue
        if re.search(r"같음", e["head"]):
            if not screens:
                errors.append(f"{n:04d}: 첫 프레임은 '같음'일 수 없습니다.")
            continue  # 직전 화면이 계속 떠 있는 것으로 본다
        if e["head"] not in KINDS:
            errors.append(f"{n:04d}: 종류 '{e['head']}'는 없습니다. {', '.join(sorted(KINDS))} 중 하나.")
        text = "\n".join(e["text"]).strip("\n")
        desc = " ".join(d for d in e["description"] if d)
        if not text and not desc:
            errors.append(f"{n:04d}: 글자도 설명도 비어 있습니다.")
        screens.append({"time": fr["time"], "kind": e["head"], "text": "" if e["head"] == "people" else text,
                        "description": desc, "image": fr["image"]})
    for extra in sorted(set(entries) - set(range(1, len(frames) + 1))):
        errors.append(f"{extra:04d}: frames.json에 없는 번호입니다.")

    if errors:
        print(f"오류 {len(errors)}개 — screens.json을 만들지 않았습니다.")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    (work / "screens.json").write_text(json.dumps({"screens": screens}, ensure_ascii=False, indent=1), encoding="utf-8")
    unread_at = [Path(s["image"]).stem for s in screens if "[읽을 수 없음]" in s["text"]]
    unread = len(unread_at)
    print(f"{work / 'screens.json'} — 프레임 {len(frames)}장 → 화면 {len(screens)}개"
          + (f" · 읽지 못한 글자가 있는 프레임: {', '.join(unread_at)}" if unread else ""))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
