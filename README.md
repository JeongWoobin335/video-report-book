# 영상 리포트북

강의·회의 영상을 올리면 음성과 화면을 함께 읽어 **리포트**를 만들고, 그 내용으로 **이해도 퀴즈**와 **요약 만화**를 만들어 영상을 실제로 이해했는지 확인해 주는 웹 서비스.

- 화면: `web/` — 정적 파일, GitHub Pages. 영상은 기기 밖으로 나가지 않고 브라우저가 음성과 주요 화면만 뽑아 보낸다.
- 백엔드: `backend/` (FastAPI) + `engine/` (Gemini 호출·검증 루프). 실행과 설정은 [backend/README.md](backend/README.md).
- 지식과 도구: `skills/` — 단계별 규칙(references)과 검증·렌더 스크립트(scripts).
- 쓰는 오픈소스·외부 API·AI와 라이선스: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- 설계와 진행 기록: [docs/skill-bundle-design.md](docs/skill-bundle-design.md)

## 로컬에서 한 번에 띄우기

```bash
pip install -r backend/requirements.txt
GEMINI_API_KEY=... SERVE_WEB=1 python -m uvicorn backend.app:app --port 8000
```

→ http://127.0.0.1:8000/web/
