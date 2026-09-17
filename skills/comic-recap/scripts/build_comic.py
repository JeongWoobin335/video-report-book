"""comic-draft.md를 검사하고 comic.json + comic.html을 만든다.

사용: python build_comic.py <작업 폴더>
읽는 것: comic-draft.md, report.json, (있으면) screens.json과 frames/    쓰는 것: comic.json, comic.html
오류가 있으면 아무것도 쓰지 않고 종료 코드 1.
"""
import base64
import json
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
NO_USE_SECTIONS = {"영상 속 자료와 발언이 다른 부분"}  # 다툼의 여지가 있는 내용은 만화에 넣지 않는다
MAX_BUBBLE = 40
SAME_MOOD = 3  # 같은 사람이 같은 표정으로 이어져도 되는 컷 수
PANELS = (4, 10)
BACKGROUNDS = {"사무실": "office", "없음": "plain"}


def to_sec(ts):
    n = [int(x) for x in ts.split(":")]
    return n[0] * 60 + n[1] if len(n) == 2 else n[0] * 3600 + n[1] * 60 + n[2]


def to_ts(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}" if sec < 3600 else f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def load_report(work):
    report = json.loads((work / "report.json").read_text(encoding="utf-8"))
    items, top = {}, None
    for sec in report["sections"]:
        if sec["level"] == 2:
            top = sec["heading"]
        for it in sec["items"]:
            items[it["id"]] = {"top": top, "text": it["text"], "timestamps": it["timestamps"]}
    # 자료와 발언이 달랐던 시각들. 그 섹션 밖의 본문 항목이 같은 내용을 담고 있을 수 있다.
    disputed = {t["start"] for it in items.values() if it["top"] in NO_USE_SECTIONS for t in it["timestamps"]}
    for it in items.values():
        it["points_to_dispute"] = it["top"] not in NO_USE_SECTIONS and "다른 부분" in it["text"]
        it["near_dispute"] = " / ".join(d["text"] for d in items.values() if d["top"] in NO_USE_SECTIONS
                                        and any(t["start"] == u["start"] for t in it["timestamps"] for u in d["timestamps"]))             if it["top"] not in NO_USE_SECTIONS else ""
    return report, items


def parse_draft(text):
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip("\"'")
        text = text[m.end():]
    panels, p = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^##\s+", line):
            p = {"label": line.lstrip("# ").strip(), "lines": []}
            panels.append(p)
        elif p is None or not line:
            continue
        elif d := re.match(r"^[-*]\s*([^()（）:]+?)\s*[(（]\s*(\w+)\s*[)）]\s*:\s*(.*)$", line):
            p["lines"].append({"name": d.group(1).strip(), "mood": d.group(2), "text": d.group(3).strip()})
        elif kv := re.match(r"^(근거|배경|내레이션)\s*:\s*(.*)", line):
            p[kv.group(1)] = kv.group(2).strip()
        else:
            p.setdefault("junk", []).append(line)
    return meta, panels


def main():
    work = Path(sys.argv[1])
    for name in ("comic-draft.md", "report.json"):
        if not (work / name).exists():
            sys.exit(f"{work / name} 가 없습니다.")
    cast = json.loads((ASSETS / "cast.json").read_text(encoding="utf-8"))
    report, items = load_report(work)
    screens = []
    if (work / "screens.json").exists():
        screens = sorted(json.loads((work / "screens.json").read_text(encoding="utf-8"))["screens"], key=lambda s: s["time"])
    disputed_times = {t["start"] for it in items.values() if it["top"] in NO_USE_SECTIONS for t in it["timestamps"]}
    meta, panels = parse_draft((work / "comic-draft.md").read_text(encoding="utf-8"))

    errors, warnings = [], []
    names = {}
    for pair in meta.get("등장인물", "").split(","):
        if "=" in pair:
            k, v = (x.strip() for x in pair.split("=", 1))
            names[k] = v
            if v not in cast["characters"]:
                errors.append(f"등장인물 '{k}'의 캐릭터 '{v}'는 없습니다. 쓸 수 있는 것: {', '.join(cast['characters'])}")
    if not names:
        errors.append("frontmatter에 '등장인물: 이름=캐릭터, …'가 없습니다.")
    if not PANELS[0] <= len(panels) <= PANELS[1]:
        errors.append(f"컷은 {PANELS[0]}~{PANELS[1]}개여야 합니다 (지금 {len(panels)}개).")

    out = []
    for n, p in enumerate(panels, 1):
        tag = f"컷 {p['label']}"
        for j in p.get("junk", []):
            errors.append(f"[{tag}] 알 수 없는 줄: \"{j[:40]}\" (대사는 '- 이름(표정): 대사' 형식)")
        sources = [s.strip() for s in p.get("근거", "").split(",") if s.strip()]
        if not sources:
            errors.append(f"[{tag}] '근거:'가 없습니다.")
        for sid in sources:
            if sid not in items:
                errors.append(f"[{tag}] 근거 {sid} 가 report.json에 없습니다.")
            elif "(확인 필요)" in items[sid]["text"]:
                errors.append(f"[{tag}] 근거 {sid} 는 '(확인 필요)'로 표시된 불확실한 내용이라 만화에 쓸 수 없습니다.")
            elif items[sid]["points_to_dispute"]:
                errors.append(f"[{tag}] 근거 {sid} 는 자료와 발언이 달랐던 내용을 담은 항목이라 만화에 쓸 수 없습니다.")
            elif items[sid]["top"] in NO_USE_SECTIONS:
                errors.append(f"[{tag}] 근거 {sid} 는 '{items[sid]['top']}' 섹션이라 만화에 쓸 수 없습니다.")
            elif "슬라이드에만" in items[sid]["text"]:
                warnings.append(f"[{tag}] 근거 {sid} 는 슬라이드에만 있던 내용입니다. 영상에서 말로 설명하지 않은 것을 대사로 만들지 마세요.")
            elif items[sid]["near_dispute"]:
                warnings.append(f"[{tag}] 근거 {sid} 와 같은 시각에 자료와 발언이 달랐던 내용이 있습니다 — \"{items[sid]['near_dispute']}\" 이 어긋난 값을 대사·내레이션에 쓰지 마세요.")

        actors = []
        for ln in p["lines"]:
            if ln["name"] not in names:
                errors.append(f"[{tag}] '{ln['name']}'는 등장인물에 없습니다.")
                continue
            if ln["mood"] not in cast["moods"]:
                errors.append(f"[{tag}] 표정 '{ln['mood']}'는 없습니다. 쓸 수 있는 것: {', '.join(cast['moods'])}")
            plain = re.sub(r"[`*]", "", ln["text"])
            if len(plain) > MAX_BUBBLE:
                warnings.append(f"[{tag}] 말풍선이 {len(plain)}자입니다 ({MAX_BUBBLE}자 이내 권장): \"{plain[:20]}…\"")
            actors.append(ln)
        who = list(dict.fromkeys(a["name"] for a in actors))
        if not who:
            errors.append(f"[{tag}] 인물이 없습니다.")
        if len(who) > 2:
            errors.append(f"[{tag}] 한 컷에 인물은 둘까지입니다 (지금 {len(who)}명).")
        if sum(1 for a in actors if a["text"]) > 3:
            warnings.append(f"[{tag}] 말풍선이 3개를 넘습니다. 컷을 나누세요.")

        bg_raw = p.get("배경", "없음")
        bg = {"kind": BACKGROUNDS.get(bg_raw, "plain")}
        if m := re.match(r"^화면\s+(\d{1,2}:\d{2}(?::\d{2})?)$", bg_raw):
            t = to_sec(m.group(1))
            sc = next((s for s in reversed(screens) if s["time"] <= t), None)
            if sc is None:
                warnings.append(f"[{tag}] {m.group(1)}에 해당하는 화면 정보가 없어 빈 배경으로 둡니다.")
            elif any(sc["time"] <= d and (nxt is None or d < nxt) for d in disputed_times for nxt in [next((s2["time"] for s2 in screens if s2["time"] > sc["time"]), None)]):
                warnings.append(f"[{tag}] {m.group(1)}의 화면에는 자료와 발언이 달랐던 내용이 적혀 있습니다. 배경을 '사무실'이나 '없음'으로 바꾸세요.")
            elif sc.get("kind") in ("people", "participants"):
                warnings.append(f"[{tag}] {m.group(1)}의 화면은 사람이나 참가자 이름표가 나온 화면이라 쓰지 않습니다.")
            else:
                img = sc.get("image")
                bg = {"kind": "screen", "time": sc["time"], "text": sc.get("text", ""),
                      "image": img if img and (work / img).exists() else None}
        elif bg_raw not in BACKGROUNDS:
            errors.append(f"[{tag}] 배경은 '사무실', '없음', '화면 mm:ss' 중 하나여야 합니다: \"{bg_raw}\"")

        stamps = [t for s in sources if s in items for t in items[s]["timestamps"]]
        out.append({
            "n": n, "sources": sources, "t": min((t["start"] for t in stamps), default=None),
            "background": bg, "narration": p.get("내레이션", ""),
            "people": [{"name": w, "character": names.get(w), "side": "left" if i == 0 else "right",
                        "mood": [a["mood"] for a in actors if a["name"] == w][-1]} for i, w in enumerate(who)],
            "bubbles": [{"name": a["name"], "side": "left" if a["name"] == who[0] else "right", "text": a["text"]}
                        for a in actors if a["text"]],
        })

    if not errors and sum(1 for p in out if p["background"]["kind"] == "screen") > 0.75 * len(out):
        warnings.append("거의 모든 컷이 화면 배경입니다. 대화·반응 컷을 섞으면 덜 단조롭습니다.")
    # 표정이 곧 포즈다 — 같은 사람이 같은 표정으로 오래 이어지면 같은 그림이 계속 찍힌다
    streak = {}
    for p in out:
        for a in p["people"]:
            last = streak.get(a["name"])
            streak[a["name"]] = (a["mood"], last[1] + 1 if last and last[0] == a["mood"] else 1, last[2] if last and last[0] == a["mood"] else p["n"])
            mood, count, since = streak[a["name"]]
            if count == SAME_MOOD + 1:
                warnings.append(f"[컷 {since}~{p['n']}] '{a['name']}'가 {count}컷째 같은 표정({mood})입니다. 같은 그림이 이어집니다 — 흐름에 맞게 표정을 바꾸세요 (think, happy, worried, neutral 등).")
    for w in warnings:
        print("경고:", w)
    if errors:
        print(f"오류 {len(errors)}개 — comic.json을 만들지 않았습니다.")
        for e in errors:
            print(" -", e)
        sys.exit(1)

    comic = {"title": meta.get("title") or f"만화로 보는 {report['title']}", "type": report["type"],
             "report_title": report["title"], "panels": out}
    for p in comic["panels"]:
        p["t_label"] = to_ts(p["t"]) if p["t"] is not None else ""
    (work / "comic.json").write_text(json.dumps(comic, ensure_ascii=False, indent=2), encoding="utf-8")

    page = (ASSETS / "comic-template.html").read_text(encoding="utf-8")
    page = page.replace("{{title}}", comic["title"].replace("<", "&lt;"))
    page = page.replace("{{characters_js}}", (ASSETS / "characters.js").read_text(encoding="utf-8"))
    page = page.replace("{{cast_json}}", json.dumps(cast, ensure_ascii=False))
    page = page.replace("{{parts_json}}", json.dumps(used_parts(cast, comic), ensure_ascii=False))
    page = page.replace("{{comic_json}}", json.dumps(comic, ensure_ascii=False).replace("</", "<\\/"))
    (work / "comic.html").write_text(page, encoding="utf-8")
    print(f"컷 {len(out)}개, 경고 {len(warnings)}개")
    print(work / "comic.json")
    print(work / "comic.html")


def used_parts(cast, comic):
    """이 만화에 나오는 (캐릭터, 표정) 조합에 필요한 그림 파츠만 data URI로 묶는다 → comic.html 한 파일로 열린다."""
    keys = set()
    for p in comic["panels"]:
        for a in p["people"]:
            c, m = cast["characters"][a["character"]], cast["moods"].get(a["mood"]) or cast["moods"]["neutral"]
            keys |= {"body/" + c["bodies"].get(a["mood"], c["bodies"]["default"]), "head/" + c["head"], "face/" + m["face"]}
    return {k: "data:image/svg+xml;base64," + base64.b64encode((ASSETS / "peeps" / f"{k}.svg").read_bytes()).decode() for k in sorted(keys)}


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
