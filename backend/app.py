"""영상 리포트 백엔드 API.

실행: GEMINI_API_KEY=... uvicorn backend.app:app --port 8000   (프로젝트 루트에서)

  POST /api/jobs                       작업 접수 — 브라우저가 뽑은 오디오+키프레임(기본), 또는 영상 파일(개발용)
  GET  /api/jobs/{id}                  진행 상태
  GET  /api/jobs/{id}/files/{name}     결과물 (정답이 든 파일은 내주지 않는다)
  POST /api/jobs/{id}/attempts         퀴즈 응답 채점 (정답은 서버에만 있다)
  GET  /api/jobs/{id}/summary          여러 응답의 집계
  GET  /api/health                     설정과 오늘 남은 처리량

설정은 모두 환경변수: GEMINI_API_KEY, GEMINI_MODELS, DAILY_JOB_LIMIT, MAX_MINUTES, MAX_FRAMES, RETENTION_HOURS,
JOBS_DIR, ALLOWED_ORIGINS(쉼표 구분, 기본 *), ALLOW_VIDEO_UPLOAD(1이면 영상 파일 직접 업로드 허용),
SERVE_WEB(1이면 web/ 화면도 함께 내준다 — 로컬 개발용. http://127.0.0.1:8000/web/ ).
"""
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import jobs

import grade as grading        # skills/quiz-grading/scripts (jobs가 경로를 잡아 둔다)  # noqa: E402
import summarize as summary    # noqa: E402

MAX_AUDIO_MB = float(os.environ.get("MAX_AUDIO_MB", 40))
MAX_FRAME_MB = 2
MAX_VIDEO_MB = float(os.environ.get("MAX_VIDEO_MB", 300))
ALLOW_VIDEO_UPLOAD = os.environ.get("ALLOW_VIDEO_UPLOAD", "1") == "1"
# 밖으로 내주는 파일. quiz.json과 quiz.html에는 정답이 들어 있으므로 내주지 않는다.
PUBLIC_FILES = re.compile(r"^(report\.html|report\.json|comic\.html|comic\.json|quiz\.public\.json|frames/\d{4}\.jpg)$")
AUDIO_EXT = {".mp3", ".m4a", ".ogg", ".webm", ".wav", ".aac"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


@asynccontextmanager
async def lifespan(_app):
    jobs.start()
    yield


app = FastAPI(title="video-report-book", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


async def save_upload(upload: UploadFile, dest: Path, limit_mb: float):
    size = 0
    with open(dest, "wb") as out:
        while chunk := await upload.read(1 << 20):
            size += len(chunk)
            if size > limit_mb * (1 << 20):
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"파일이 너무 큽니다 (최대 {limit_mb:.0f}MB).")
            out.write(chunk)
    return size


def public(status: dict):
    """상태에서 밖에 보여 줄 것만 추린다."""
    keep = ("id", "state", "stage", "stages", "title", "type", "created_at", "finished_at", "error", "failed_parts", "outputs")
    out = {k: status.get(k) for k in keep}
    out["queue_position"] = jobs.queue_position(status["id"]) if status["state"] == "queued" else 0
    return out


@app.get("/api/health")
def health():
    used = jobs.used_today()
    return {"ok": True, "has_key": bool(os.environ.get("GEMINI_API_KEY")),
            "today": {"used": used, "limit": jobs.DAILY_JOB_LIMIT, "left": max(jobs.DAILY_JOB_LIMIT - used, 0)},
            "limits": {"max_minutes": jobs.MAX_MINUTES, "max_frames": jobs.MAX_FRAMES, "max_audio_mb": MAX_AUDIO_MB,
                       "retention_hours": jobs.RETENTION_HOURS, "video_upload": ALLOW_VIDEO_UPLOAD}}


@app.post("/api/jobs", status_code=202)
async def create_job(
    consent: str = Form(...),
    meta: str = Form("{}"),
    audio: Optional[UploadFile] = File(None),
    frames: List[UploadFile] = File(default=[]),
    video: Optional[UploadFile] = File(None),
):
    """meta(JSON): {"duration": 초, "title": "", "language": "ko", "type": null|"meeting"|"education"|"general", "frame_times": [초, …]}"""
    if consent != "true":
        raise HTTPException(400, "올리는 영상에 기밀이나 타인의 개인정보가 없고, 내용이 AI 서비스로 전송되어 처리된다는 점에 동의해야 합니다.")
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(503, "서버에 AI 키가 설정되지 않았습니다.")
    jobs.cleanup()
    if jobs.used_today() >= jobs.DAILY_JOB_LIMIT:
        raise HTTPException(429, f"오늘 처리할 수 있는 영상 수({jobs.DAILY_JOB_LIMIT}편)를 다 썼습니다. 내일 다시 시도해 주세요.")
    try:
        m = json.loads(meta or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "meta는 JSON이어야 합니다.")
    kind = m.get("type") if m.get("type") in pipeline_types() else None
    title = str(m.get("title") or "")[:120]

    if video is not None:  # 개발용: 서버가 ffmpeg로 오디오·키프레임을 뽑는다
        if not ALLOW_VIDEO_UPLOAD:
            raise HTTPException(400, "영상 파일은 받지 않습니다. 브라우저에서 뽑은 오디오와 키프레임을 보내 주세요.")
        ext = Path(video.filename or "").suffix.lower()
        if ext not in VIDEO_EXT:
            raise HTTPException(400, f"지원하지 않는 영상 형식입니다: {ext}")
        job_id = jobs.create(title or Path(video.filename).stem, kind, m.get("language") or "ko", has_video_file=True)
        await save_upload(video, jobs.job_dir(job_id) / f"upload{ext}", MAX_VIDEO_MB)
    else:
        duration = float(m.get("duration") or 0)
        times = m.get("frame_times") or []
        if audio is None and not frames:
            raise HTTPException(400, "오디오나 키프레임 중 하나는 있어야 합니다.")
        if duration <= 0:
            raise HTTPException(400, "meta.duration(영상 길이, 초)이 필요합니다.")
        if duration > jobs.MAX_MINUTES * 60:
            raise HTTPException(400, f"영상이 너무 깁니다. 지금은 {jobs.MAX_MINUTES:.0f}분까지 받습니다.")
        if len(frames) > jobs.MAX_FRAMES or len(times) != len(frames):
            raise HTTPException(400, f"키프레임은 {jobs.MAX_FRAMES}장까지이고, meta.frame_times의 개수와 같아야 합니다.")
        job_id = jobs.create(title, kind, m.get("language") or "ko", has_video_file=False)
        work = jobs.job_dir(job_id)
        if audio is not None:
            ext = Path(audio.filename or "").suffix.lower()
            if ext not in AUDIO_EXT:
                raise HTTPException(400, f"지원하지 않는 오디오 형식입니다: {ext}")
            await save_upload(audio, work / f"audio{ext}", MAX_AUDIO_MB)
        (work / "frames").mkdir()
        listing = []
        for n, (fr, t) in enumerate(sorted(zip(frames, times), key=lambda x: float(x[1])), 1):
            name = f"frames/{n:04d}.jpg"  # 올린 쪽이 붙인 파일 이름은 쓰지 않는다
            await save_upload(fr, work / name, MAX_FRAME_MB)
            listing.append({"time": round(float(t), 1), "image": name})
        (work / "frames.json").write_text(json.dumps(listing), encoding="utf-8")
        (work / "info.json").write_text(json.dumps({"source": title, "duration": duration, "has_audio": audio is not None,
                                                    "has_video": bool(frames)}), encoding="utf-8")
    jobs.enqueue(job_id)
    return public(jobs.read_status(job_id))


def pipeline_types():
    return jobs.pipeline.TYPES


def get_status(job_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,40}", job_id):
        raise HTTPException(404, "없는 작업입니다.")
    status = jobs.read_status(job_id)
    if not status:
        raise HTTPException(404, "없는 작업입니다. 보관 기간이 지나 지워졌을 수 있습니다.")
    return status


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return public(get_status(job_id))


@app.get("/api/jobs/{job_id}/files/{name:path}")
def job_file(job_id: str, name: str):
    get_status(job_id)
    if not PUBLIC_FILES.fullmatch(name):
        raise HTTPException(404, "없는 파일입니다.")
    path = jobs.job_dir(job_id) / name
    if not path.exists():
        raise HTTPException(404, "아직 만들어지지 않았습니다.")
    return FileResponse(path)


# 로컬 개발용: SERVE_WEB=1 이면 화면(web/)과 샘플(samples/)도 이 서버가 내준다 → 명령 하나로 전체가 뜬다.
# 배포할 때는 화면은 github.io가, API는 이 서버가 맡으므로 켜지 않는다.
if os.environ.get("SERVE_WEB") == "1":
    from fastapi.staticfiles import StaticFiles
    app.mount("/web", StaticFiles(directory=jobs.ROOT / "web", html=True), name="web")
    if (jobs.ROOT / "samples").exists():
        app.mount("/samples", StaticFiles(directory=jobs.ROOT / "samples"), name="samples")


class Attempt(BaseModel):
    answers: dict
    respondent: Optional[str] = None


@app.post("/api/jobs/{job_id}/attempts")
def submit_attempt(job_id: str, attempt: Attempt):
    """채점해서 돌려준다. 제출한 뒤에는 정답과 해설, 다시 볼 구간을 알려준다."""
    get_status(job_id)
    work = jobs.job_dir(job_id)
    if not (work / "quiz.json").exists():
        raise HTTPException(404, "이 작업에는 퀴즈가 없습니다.")
    quiz = json.loads((work / "quiz.json").read_text(encoding="utf-8"))
    response = {"respondent": (attempt.respondent or "익명")[:40], "submitted_at": jobs.now(),
                "answers": {k: str(v)[:4] for k, v in list(attempt.answers.items())[:50]}}
    (work / "answers").mkdir(exist_ok=True)
    n = len(list((work / "answers").glob("*.json"))) + 1
    (work / "answers" / f"{n:04d}.json").write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    result = grading.grade_one(quiz, response)
    explain = {q["id"]: q["explanation"] for q in quiz["items"]}
    for row in result["items"]:
        row["explanation"] = explain[row["id"]]
    if quiz["type"] == "meeting":  # 회의는 점수를 매기지 않는다
        result.pop("by_checks", None)
    return result


@app.get("/api/jobs/{job_id}/summary")
def job_summary(job_id: str):
    get_status(job_id)
    work = jobs.job_dir(job_id)
    if not list((work / "answers").glob("*.json")) if (work / "answers").exists() else True:
        raise HTTPException(404, "아직 제출된 응답이 없습니다.")
    quiz, results = grading.grade_all(work)
    return summary.summarize(quiz, results)
