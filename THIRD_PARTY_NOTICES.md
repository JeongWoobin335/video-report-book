# 외부 자원과 라이선스

이 프로젝트가 쓰는 오픈소스·외부 API·생성형 AI와 각각의 이용 조건, 그리고 그 조건을 어떻게 지키고 있는지 적는다.

## 서비스가 동작할 때 쓰는 것

| 자원 | 쓰는 곳 | 라이선스·약관 | 지키는 방법 |
|---|---|---|---|
| **Google Gemini API** (무료 등급) — `gemini-*-flash`, `gemini-*-flash-lite` | 전사, 화면 읽기, 리포트·퀴즈·만화 대본 작성 (`engine/`) | [Google APIs 서비스 약관](https://developers.google.com/terms), [Gemini API 추가 약관](https://ai.google.dev/gemini-api/terms) | 무료 등급은 입력이 Google 제품 개선에 쓰이고 사람이 검토할 수 있으므로, 올리기 전에 그 사실을 알리고 동의를 받는다. 기밀·개인정보가 든 영상은 올리지 말라고 안내한다. API 키는 서버 환경변수에만 두고 저장소·브라우저에 넣지 않는다. |
| **lamejs** 1.2.0 | 브라우저에서 MP3 인코딩 (`web/vendor/lame.min.js`) | LGPL-3.0 | 수정 없이 별도 파일로 포함(다른 빌드로 바꿔 끼울 수 있음). 출처와 라이선스를 `web/vendor/README.md`에 표기, 패키지의 라이선스 안내문을 `web/vendor/lamejs-LICENSE.txt`로 동봉. 전문: https://www.gnu.org/licenses/lgpl-3.0.html |
| **Open Peeps** (Pablo Stanley) | 만화·메인 화면의 인물 그림 (`skills/comic-recap/assets/peeps/`, `web/img/peeps/`) | CC0 1.0 (의무 없음) | 의무는 없지만 화면 바닥과 만화 아래에 출처를 표기. `Pointing Up` 한 파일은 캔버스 폭만 넓혔음을 README에 기록. |
| **Gaegu**, **Jua** 글꼴 | 만화·화면의 제목과 말풍선 (Google Fonts에서 불러옴) | SIL Open Font License 1.1 | 글꼴 파일을 재배포하지 않고 Google Fonts에서 직접 불러온다. |
| **FastAPI** / **Pydantic** | 백엔드 API | MIT | 패키지를 그대로 설치해 사용 (`backend/requirements.txt`). |
| **Uvicorn** | 백엔드 서버 | BSD-3-Clause | 위와 같음. |
| **python-multipart** | 파일 업로드 처리 | Apache-2.0 | 위와 같음. |
| **FFmpeg** | 서버에서 오디오를 조각내고 변환 | LGPL-2.1+ / GPL (빌드에 따라) | 코드에 링크하지 않고 데비안 패키지의 실행 파일을 별도 프로세스로 호출한다 (`Dockerfile`). |
| **Python** 3.11 | 백엔드·스크립트 | PSF License | — |
| **Render** (무료 웹 서비스), **GitHub Pages** | 백엔드·화면 호스팅 | 각 서비스 이용약관 | 무료 플랜의 범위 안에서 사용. |

## 개발·시험에만 쓴 것 (배포된 서비스에는 들어 있지 않음)

| 자원 | 쓴 곳 | 라이선스·약관 |
|---|---|---|
| **Claude Code** (Anthropic Claude) | 설계, 코드·프롬프트·문서 작성, 시험 | Anthropic 이용약관 — 산출물의 권리는 사용자에게 있음 |
| **faster-whisper** + Whisper `large-v3-turbo` 모델 | 로컬 전사 시험 (`skills/speech-transcribe/`) — Gemini 전사와 비교하는 기준으로 사용 | MIT (코드·모델 가중치) |
| **Pillow** | 키프레임 비교, 샘플 영상의 슬라이드 그리기 | MIT-CMU (HPND) |
| **Windows 음성 합성** (Microsoft Heami) | 샘플 강의 영상 `samples/lecture-http-caching.mp4`의 내레이션 | Windows 사용권 계약 |

## 샘플·예시 데이터

`samples/lecture-http-caching.mp4`와 `web/demo/`의 결과물, `skills/*/evals/`의 입력은 모두 **이 프로젝트를 위해 직접 만든 가상 자료**다(대본 직접 작성, 슬라이드는 코드로 그림, 음성은 합성). 실제 사람의 영상·음성·회의 내용은 저장소에 없다.
