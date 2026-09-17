"""Gemini 호출부. 표준 라이브러리만 쓴다.

- 모델 목록을 차례로 시도한다. 무료 등급은 수요가 몰리면 503, 한도를 넘으면 429를 낸다 → 기다리지 않고 다음 모델로 넘어간다.
- 한 번 응답한 모델을 그 실행 동안 계속 쓴다(단계마다 모델이 바뀌면 문체가 흔들린다).
- 호출마다 토큰 사용량을 기록한다.
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 앞의 것부터 시도한다. 무료 등급에서 Flash 계열은 모델당 하루 20회, Lite 계열은 하루 500회(2026-09 기준)라 Lite를 마지막 보루로 둔다.
# GEMINI_MODELS 환경변수(쉼표 구분)로 바꿀 수 있다 — 유료 키로 갈아탈 때는 키와 이 목록만 바꾸면 된다.
DEFAULT_MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()] or [
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".wav": "audio/wav", ".mp3": "audio/mp3", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}


class LLMError(RuntimeError):
    pass


class Gemini:
    def __init__(self, models=None, api_key=None):
        self.models = list(models or DEFAULT_MODELS)
        self.key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.key:
            raise LLMError("GEMINI_API_KEY 환경변수가 없습니다.")
        self.usage = []      # [{stage, model, in, out, thinking, sec}]
        self.skipped = {}    # 이번 실행에서 응답하지 않은 모델 → 사유
        self.no_system = set()  # 시스템 지침 칸을 받지 않는 모델 (전사 전용 모델, Gemma 등) → 지침을 사용자 메시지 앞에 붙인다

    def generate(self, system, user, stage="", files=(), temperature=0.3, max_output=16000):
        """system/user는 글, files는 함께 보낼 이미지·오디오 경로들. 응답 글을 돌려준다."""
        # user가 목록이면 글과 파일을 적힌 순서대로 섞어 보낸다: ["프레임 0001:", Path("frames/0001.jpg"), "프레임 0002:", …]
        def part(x):
            if isinstance(x, str):
                return {"text": x}
            with open(x, "rb") as fh:
                return {"inlineData": {"mimeType": MIME[os.path.splitext(str(x))[1].lower()], "data": base64.b64encode(fh.read()).decode()}}
        parts = [part(x) for x in (list(files) + (list(user) if isinstance(user, (list, tuple)) else [user]))]
        config = {"temperature": temperature, "maxOutputTokens": max_output}

        for model in [m for m in self.models if m not in self.skipped]:
            for attempt in range(3):
                if model in self.no_system or model.startswith("gemma"):
                    body = {"contents": [{"role": "user", "parts": [{"text": system + "\n\n---\n"}] + parts}], "generationConfig": config}
                else:
                    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}], "generationConfig": config}
                payload = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(API.format(model=model), data=payload,
                                             headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})
                t0 = time.time()
                try:
                    data = json.load(urllib.request.urlopen(req, timeout=300))
                except urllib.error.HTTPError as e:
                    err = e.read().decode("utf-8", "replace")
                    status = (json.loads(err).get("error", {}) if err.startswith("{") else {}).get("status", "")
                    if e.code == 400 and "Developer instruction" in err and model not in self.no_system:
                        self.no_system.add(model)
                        continue
                    if e.code == 500 and attempt == 0:   # 일시적인 내부 오류는 한 번만 다시
                        time.sleep(3)
                        continue
                    if e.code in (429, 500, 503):        # 혼잡·한도 초과 → 이 모델은 접고 다음 모델로
                        self.skipped[model] = f"{e.code} {status}"
                        break
                    raise LLMError(f"{model}: HTTP {e.code} {err[:300]}")
                except (urllib.error.URLError, TimeoutError) as e:
                    self.skipped[model] = f"연결 실패: {e}"
                    break
                cand = (data.get("candidates") or [{}])[0]
                text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
                if not text.strip():
                    self.skipped[model] = f"빈 응답 ({cand.get('finishReason')})"
                    break
                u = data.get("usageMetadata", {})
                self.usage.append({"stage": stage, "model": model, "in": u.get("promptTokenCount", 0),
                                   "out": u.get("candidatesTokenCount", 0), "thinking": u.get("thoughtsTokenCount", 0),
                                   "sec": round(time.time() - t0, 1)})
                self.models = [model] + [m for m in self.models if m != model]  # 응답한 모델을 맨 앞으로
                return strip_fence(text)
        raise LLMError("응답하는 모델이 없습니다: " + ", ".join(f"{m}({why})" for m, why in self.skipped.items()))

    def totals(self):
        t = {k: sum(u[k] for u in self.usage) for k in ("in", "out", "thinking", "sec")}
        t["calls"] = len(self.usage)
        t["models"] = sorted({u["model"] for u in self.usage})
        return t


def strip_fence(text):
    """모델이 답을 ```markdown … ```로 감싸는 버릇을 벗긴다."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*\n", "", text)
    return re.sub(r"\n```\s*$", "", text).strip()
