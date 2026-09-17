"""작업 저장소와 작업자. 한 영상 = 한 작업 = 한 폴더(data/jobs/<id>/).

작업자는 하나뿐이다 — 무료 등급의 분당 호출 한도가 작아서 동시에 여러 편을 돌리면 서로 막힌다.
진행 상태는 폴더 안의 status.json에 적는다. 서버가 다시 떠도 상태를 읽을 수 있고, 다른 저장소가 필요 없다.
"""
import json
import os
import queue
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "skills" / "quiz-grading" / "scripts"))

import pipeline  # noqa: E402
import screens  # noqa: E402
import transcribe  # noqa: E402
from llm import Gemini, LLMError  # noqa: E402

JOBS_DIR = Path(os.environ.get("JOBS_DIR", ROOT / "data" / "jobs"))
RETENTION_HOURS = float(os.environ.get("RETENTION_HOURS", 24))     # 이 시간이 지난 작업은 지운다
DAILY_JOB_LIMIT = int(os.environ.get("DAILY_JOB_LIMIT", 30))       # 하루에 받는 작업 수 (모든 사용자 합쳐서)
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", 30))            # 받는 영상의 최대 길이
MAX_FRAMES = int(os.environ.get("MAX_FRAMES", 40))

STAGES = [("ingest", "영상 준비"), ("screens", "화면 읽기"), ("transcribe", "음성 전사"),
          ("report", "리포트 작성"), ("quiz", "퀴즈 만들기"), ("comic", "만화 만들기")]
_queue: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def read_status(job_id: str):
    f = job_dir(job_id) / "status.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def write_status(job_id: str, **changes):
    with _lock:
        status = read_status(job_id) or {}
        status.update(changes)
        tmp = job_dir(job_id) / "status.json.tmp"
        tmp.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(job_dir(job_id) / "status.json")
    return status


def set_stage(job_id: str, key: str, state: str):
    status = read_status(job_id)
    for st in status["stages"]:
        if st["key"] == key:
            st["state"] = state
    write_status(job_id, stage=key if state == "running" else status.get("stage"), stages=status["stages"])


def all_statuses():
    if not JOBS_DIR.exists():
        return []
    return [s for s in (read_status(d.name) for d in JOBS_DIR.iterdir() if d.is_dir()) if s]


def used_today():
    today = now()[:10]
    return sum(1 for s in all_statuses() if s.get("created_at", "")[:10] == today)


def cleanup():
    """보관 기간이 지난 작업을 지운다. 회의·강의 내용이 서버에 오래 남지 않게 한다."""
    if not JOBS_DIR.exists():
        return
    limit = time.time() - RETENTION_HOURS * 3600
    for d in JOBS_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < limit:
            shutil.rmtree(d, ignore_errors=True)


def create(title: str, kind, language: str, has_video_file: bool):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_id = secrets.token_urlsafe(16)  # 로그인이 없으므로, 추측할 수 없는 ID가 곧 열쇠다
    job_dir(job_id).mkdir()
    stages = [{"key": k, "label": label, "state": "pending"} for k, label in STAGES if k != "ingest" or has_video_file]
    write_status(job_id, id=job_id, state="queued", stage=None, stages=stages, title=title, type=kind, language=language,
                 created_at=now(), error=None, failed_parts=[], outputs=[])
    return job_id


def enqueue(job_id: str):
    _queue.put(job_id)


def queue_position(job_id: str):
    waiting = [s["id"] for s in sorted(all_statuses(), key=lambda s: s["created_at"]) if s["state"] == "queued"]
    return waiting.index(job_id) + 1 if job_id in waiting else 0


def process(job_id: str):
    work = job_dir(job_id)
    status = write_status(job_id, state="running", started_at=now())
    llm = Gemini()
    try:
        if any(st["key"] == "ingest" for st in status["stages"]):
            set_stage(job_id, "ingest", "running")
            video = next(work.glob("upload.*"))
            r = subprocess.run([sys.executable, str(ROOT / "skills/video-ingest/scripts/ingest.py"), str(video), "--work", str(work),
                                "--max-frames", str(MAX_FRAMES)], capture_output=True, text=True, encoding="utf-8")
            video.unlink(missing_ok=True)  # ingest가 video.*로 복사해 두었다
            if r.returncode:
                raise RuntimeError("영상을 읽지 못했습니다: " + (r.stdout + r.stderr)[-300:])
            info = json.loads((work / "info.json").read_text(encoding="utf-8"))
            if info["duration"] > MAX_MINUTES * 60:
                raise RuntimeError(f"영상이 너무 깁니다 ({info['duration'] / 60:.0f}분). 지금은 {MAX_MINUTES:.0f}분까지 받습니다.")
            set_stage(job_id, "ingest", "done")

        set_stage(job_id, "screens", "running")
        screens.run(work, llm) or write_status(job_id, failed_parts=read_status(job_id)["failed_parts"] + ["screens"])
        set_stage(job_id, "screens", "done")

        set_stage(job_id, "transcribe", "running")
        transcribe.run(work, llm, language=status.get("language") or "ko")
        set_stage(job_id, "transcribe", "done")

        def on_stage(name, seen=[]):
            for prev in seen:
                set_stage(job_id, prev, "done")
            seen[:] = [name]
            set_stage(job_id, name, "running")

        failed = pipeline.run(work, llm, kind=status.get("type"), on_stage=on_stage)
        for key in ("report", "quiz", "comic"):
            set_stage(job_id, key, "failed" if key in failed else "done")
        outputs = [n for n in ("report", "quiz", "comic") if (work / f"{n}.json").exists()]
        report = json.loads((work / "report.json").read_text(encoding="utf-8"))
        write_status(job_id, state="done", stage=None, outputs=outputs, title=report.get("title") or status["title"], type=report.get("type"),
                     failed_parts=read_status(job_id)["failed_parts"] + failed)
    except LLMError as e:
        write_status(job_id, state="failed", error="AI 모델이 지금 응답하지 않습니다(무료 한도 소진 또는 혼잡). 나중에 다시 시도해 주세요.", detail=str(e))
    except SystemExit as e:   # 진행기가 "리포트가 검증을 통과하지 못했다" 등으로 멈춘 경우
        write_status(job_id, state="failed", error="리포트를 만들지 못했습니다.", detail=str(e)[-500:])
    except Exception as e:    # noqa: BLE001 — 한 작업의 실패가 작업자를 죽이면 안 된다
        traceback.print_exc()
        write_status(job_id, state="failed", error=str(e)[:300])
    finally:
        t = llm.totals()
        write_status(job_id, finished_at=now(), usage={k: t[k] for k in ("calls", "in", "out", "thinking", "sec", "models", "by_stage")},
                     skipped_models=llm.skipped)
        for leftover in ("audio.wav",):  # 결과를 만드는 데 더는 필요 없는 큰 파일
            (work / leftover).unlink(missing_ok=True)


def worker():
    while True:
        job_id = _queue.get()
        try:
            if read_status(job_id):
                process(job_id)
        finally:
            _queue.task_done()


def start():
    cleanup()
    for s in all_statuses():  # 서버가 꺼지는 바람에 끊긴 작업은 실패로 표시한다 (조용히 멈춰 있지 않게)
        if s["state"] in ("queued", "running"):
            write_status(s["id"], state="failed", error="서버가 다시 시작되어 작업이 중단됐습니다. 다시 올려 주세요.")
    threading.Thread(target=worker, daemon=True, name="job-worker").start()
