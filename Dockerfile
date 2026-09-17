# 영상 리포트 백엔드. 무료 호스팅(Render 등)에 그대로 올릴 수 있는 형태.
FROM python:3.11-slim

# ffmpeg: 오디오를 전사용으로 줄이고 자르는 데 쓴다 (영상 파일을 직접 받을 때는 키프레임 추출에도)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt pillow

COPY backend backend
COPY engine engine
COPY skills skills

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 JOBS_DIR=/tmp/jobs
# 키와 설정은 호스팅 서비스의 환경변수(Secret)로 넣는다: GEMINI_API_KEY, GEMINI_MODELS, DAILY_JOB_LIMIT, ALLOWED_ORIGINS …
CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
