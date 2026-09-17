# 백엔드

`engine/`(진행기)을 감싸는 작은 API 서버. 작업을 받아 대기열에 넣고, 한 번에 한 편씩 처리하고, 진행 상태와 결과물을 내준다.

## 로컬 실행

프로젝트 루트에서:

```bash
pip install -r backend/requirements.txt
```

```bash
GEMINI_API_KEY=... python -m uvicorn backend.app:app --port 8000
```

ffmpeg가 PATH에 있어야 한다.

## API

| 메서드·경로 | 하는 일 |
|---|---|
| `GET /api/health` | 키 설정 여부, 오늘 남은 처리 편수, 제한값 |
| `POST /api/jobs` | 작업 접수 (multipart). 아래 참고 |
| `GET /api/jobs/{id}` | 진행 상태 — `state`(queued/running/done/failed), 단계별 상태, 대기 순번, 오류 |
| `GET /api/jobs/{id}/files/{name}` | 결과물: `report.html`, `report.json`, `comic.html`, `comic.json`, `quiz.public.json`, `frames/0001.jpg` … |
| `POST /api/jobs/{id}/attempts` | 퀴즈 응답 `{"answers": {"q1": "b"}, "respondent": "이름"}` → 채점 결과, 해설, 다시 볼 구간 |
| `GET /api/jobs/{id}/summary` | 제출된 응답들의 집계 (문항별 정답률·보기 분포·살펴볼 문항) |

### 작업 접수

영상은 서버로 올리지 않는 것이 기본이다. 브라우저가 영상에서 오디오와 키프레임을 뽑아 보낸다.

- `consent` = `"true"` (필수 — 기밀·타인의 개인정보가 없고, 내용이 AI 서비스로 전송됨에 동의)
- `meta` = JSON: `{"duration": 257.9, "title": "…", "language": "ko", "type": null, "frame_times": [0, 8, 30, …]}`
- `audio` = 오디오 파일 (mp3, m4a, ogg, webm, wav, aac)
- `frames` = 키프레임 jpg 여러 장 (`frame_times`와 같은 순서·개수)

개발용으로 `video`에 영상 파일을 직접 올릴 수도 있다(`ALLOW_VIDEO_UPLOAD=1`일 때). 이 경우 서버가 ffmpeg로 오디오와 키프레임을 뽑는다.

`quiz.json`과 `quiz.html`은 정답이 들어 있어 내주지 않는다. 화면은 `quiz.public.json`으로 문제를 그리고 `attempts`로 채점받는다.

## 설정 (환경변수)

| 이름 | 기본값 | 뜻 |
|---|---|---|
| `GEMINI_API_KEY` | — | 모델 키. **무료 키에서 유료 키로 바꿀 때는 이것과 `GEMINI_MODELS`만 바꾸면 된다** |
| `GEMINI_MODELS` | Flash 5종 → Lite 2종 | 시도할 모델(쉼표 구분, 앞의 것부터). 503·429가 나면 다음 모델로 넘어간다 |
| `DAILY_JOB_LIMIT` | 30 | 하루에 받는 작업 수 (모든 사용자 합쳐서) — 무료 한도와 예산을 지키는 장치 |
| `MAX_MINUTES` | 30 | 받는 영상의 최대 길이 |
| `MAX_FRAMES` | 40 | 키프레임 최대 장수 |
| `MAX_AUDIO_MB` / `MAX_VIDEO_MB` | 40 / 300 | 업로드 크기 제한 |
| `RETENTION_HOURS` | 24 | 이 시간이 지난 작업 폴더는 지운다 |
| `JOBS_DIR` | `data/jobs` | 작업 폴더 위치 |
| `ALLOWED_ORIGINS` | `*` | 화면을 올린 주소(예: `https://아이디.github.io`). 공개할 때는 반드시 좁힌다 |
| `ALLOW_VIDEO_UPLOAD` | 1 | 0이면 영상 파일 직접 업로드를 막는다 |

## 배포

루트의 `Dockerfile`로 이미지를 만든다. 키는 이미지에 넣지 않고 호스팅 서비스의 환경변수(Secret)로 넣는다.

무료 호스팅에서 알아둘 것:
- 쓰지 않으면 잠들고, 첫 요청에 수십 초가 걸린다.
- 디스크가 임시라서 잠들었다 깨어나면 작업 폴더가 사라진다 → 결과물은 "만들고 바로 받아 가는" 것으로 생각해야 한다. 오래 보관하려면 별도 저장소가 필요하다.
- 작업자가 하나이므로 동시에 여러 편이 들어오면 순서대로 처리된다(상태의 `queue_position`).

## 아직 없는 것

- 로그인·사용자별 횟수 제한 (지금은 하루 전체 상한과 추측할 수 없는 작업 ID뿐)
- 남용 방지(IP별 제한, 캡차)
- 결과물의 장기 보관, 공유 링크
