"""작업 폴더가 파이프라인의 어디까지 와 있는지 알려준다.

사용: python status.py <작업 폴더>
"""
import sys
from pathlib import Path

# (단계 이름, 스킬, 끝났다는 표시, 이 단계가 기대는 표시들)
STAGES = [
    ("영상 받아들이기", "video-ingest", "frames.json", []),
    ("음성 전사", "speech-transcribe", "transcript.json", ["info.json"]),
    ("화면 읽기", "screen-read", "screens.json", ["frames.json"]),
    ("통합 리포트", "integrated-report", "report.json", ["transcript.json", "screens.json"]),
    ("이해도 퀴즈", "comprehension-quiz", "quiz.json", ["report.json"]),
    ("만화 요약", "comic-recap", "comic.json", ["report.json"]),
    ("모아보기 페이지", "video-report-pipeline", "index.html", ["report.json"]),
]


def main():
    work = Path(sys.argv[1])
    if not work.exists():
        print(f"{work} 가 아직 없습니다 → 1단계(video-ingest)부터 시작하세요:")
        print(f"  python ../video-ingest/scripts/ingest.py <영상 파일> --work {work}")
        return
    ready = []
    for n, (name, skill, marker, needs) in enumerate(STAGES, 1):
        f = work / marker
        if f.exists():
            # 기대는 파일이 이 결과물보다 나중에 바뀌었으면, 옛 입력으로 만든 결과물이다
            stale = [d for d in needs if (work / d).exists() and (work / d).stat().st_mtime > f.stat().st_mtime + 1]
            state = f"오래됨 — {', '.join(stale)} 가 더 새것. 다시 만드세요" if stale else "끝남"
            if stale:
                ready.append(f"{n}. {name} ({skill})")
        elif all((work / d).exists() for d in needs):
            state = "할 차례"
            ready.append(f"{n}. {name} ({skill})")
        else:
            state = "대기 — " + ", ".join(d for d in needs if not (work / d).exists()) + " 필요"
        print(f"{n}. {name:<10} {state}")
    print()
    print("지금 할 수 있는 단계: " + (" / ".join(ready) if ready else "없음 — 모두 끝났습니다."))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):  # 콘솔 설정과 무관하게 한글이 깨지지 않도록
        _s.reconfigure(encoding="utf-8")
    main()
