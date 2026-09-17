"""integrated-report 스크립트들이 같이 쓰는 것: 시각 변환, 입력 읽기, draft.md 파싱."""
import json
import re
import sys
from pathlib import Path

# [03:02], [1:03:02], [03:02–03:40] (구분자는 – - ~ 모두 허용)
TS = r"\d{1,2}:\d{2}(?::\d{2})?"
TS_RE = re.compile(rf"\[({TS})(?:\s*[–—\-~]\s*({TS}))?\]")

SUMMARY_TITLES = {"한눈에 보기"}
TYPES = {"meeting": "회의", "education": "교육·강의", "general": "일반"}


def to_sec(ts: str) -> int:
    n = [int(p) for p in ts.split(":")]
    return n[0] * 60 + n[1] if len(n) == 2 else n[0] * 3600 + n[1] * 60 + n[2]


def to_ts(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def load_inputs(work: Path):
    """(segments, screens, duration). 파일이 없으면 빈 목록."""
    def read(name):
        p = work / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    t, s = read("transcript.json"), read("screens.json")
    segments = sorted(t.get("segments", []), key=lambda x: x["start"])
    screens = sorted(s.get("screens", []), key=lambda x: x["time"])
    if not segments and not screens:
        sys.exit(f"{work} 에 transcript.json도 screens.json도 없습니다.")
    duration = t.get("duration") or max(
        [x["end"] for x in segments] + [x["time"] for x in screens]
    )
    return segments, screens, duration


def screen_at(screens, t):
    """t 시각에 떠 있던 화면 (없으면 None)."""
    current = None
    for sc in screens:
        if sc["time"] <= t:
            current = sc
        else:
            break
    return current


def parse_report(text: str):
    """draft.md → {meta, title, summary, sections}.

    sections: [{heading, level, items: [{text, timestamps: [{start, end}]}]}]
    level 2 = ##, level 3 = ###. 불릿의 이어지는 줄(들여쓴 줄)은 같은 항목에 붙인다.
    표의 행도 항목이다: {text, cells, header, timestamps}.
    """
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip("\"'")
        text = text[m.end():]

    title, summary, sections = None, [], []
    current, in_summary, item = None, False, None
    table_header = None
    for raw in text.splitlines():
        line = raw.rstrip()
        is_table = line.lstrip().startswith("|")
        if not is_table:
            table_header = None
        h = re.match(r"^(#{1,3})\s+(.*)", line)
        if h:
            item = None
            level, heading = len(h.group(1)), h.group(2).strip()
            if level == 1:
                title = heading
                continue
            in_summary = heading in SUMMARY_TITLES
            if not in_summary:
                current = {"heading": heading, "level": level, "items": []}
                sections.append(current)
            continue
        if not line.strip():
            item = None
            continue
        if is_table and current is not None and not in_summary:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue  # 머리글 아래 구분선
            if table_header is None:
                table_header = cells  # 표의 첫 줄은 머리글
                continue
            # 표의 행 하나 = 항목 하나. 불릿과 똑같이 타임스탬프를 검사받는다.
            current["items"].append({"text": " — ".join(c for c in cells if c), "cells": cells, "header": table_header})
            item = None
            continue
        b = re.match(r"^\s*[-*]\s+(.*)", line)
        if in_summary:
            summary.append(b.group(1) if b else line.strip())
        elif current is not None:
            if b:
                item = {"text": b.group(1)}
                current["items"].append(item)
            elif item is not None:
                item["text"] += " " + line.strip()
            else:  # 섹션 안의 줄글 — 불릿이 아니므로 검사에서 지적한다
                current["items"].append({"text": line.strip(), "prose": True})

    for sec in sections:
        for it in sec["items"]:
            it["timestamps"] = [
                {"start": to_sec(a), "end": to_sec(b) if b else None}
                for a, b in TS_RE.findall(it["text"])
            ]
    return {"meta": meta, "title": title or meta.get("title"), "summary": " ".join(summary), "sections": sections}
