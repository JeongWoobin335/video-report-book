// 브라우저 안에서 영상 → 키프레임(jpg) + 오디오(mp3). 영상 파일은 기기 밖으로 나가지 않는다.
// 서버의 skills/video-ingest/scripts/ingest.py와 같은 방식이다: 일정 간격으로 작게 훑어 보고,
// 직전에 고른 프레임과 그림이 충분히 달라졌을 때만 고른 뒤, 그 시각의 프레임을 큰 크기로 다시 뽑는다.

const HASH = 16;            // 지각 해시의 한 변 (16×16 = 256비트)

function once(target, event) {
  return new Promise((resolve, reject) => {
    const ok = () => { cleanup(); resolve(); };
    const bad = () => { cleanup(); reject(new Error(target.error ? target.error.message : event + " 실패")); };
    const cleanup = () => { target.removeEventListener(event, ok); target.removeEventListener("error", bad); };
    target.addEventListener(event, ok, { once: true });
    target.addEventListener("error", bad, { once: true });
  });
}

async function seek(video, t) {
  const done = once(video, "seeked");
  video.currentTime = t;
  await done;
}

function dhash(video, ctx) {
  // 가로로 이웃한 칸의 밝기를 비교한 비트열. 두 해시에서 다른 비트의 수가 그림의 차이다.
  ctx.drawImage(video, 0, 0, HASH + 1, HASH);
  const px = ctx.getImageData(0, 0, HASH + 1, HASH).data;
  const gray = (i) => px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114;
  const bits = new Uint8Array(HASH * HASH);
  for (let r = 0; r < HASH; r++)
    for (let c = 0; c < HASH; c++)
      bits[r * HASH + c] = gray(r * (HASH + 1) + c) > gray(r * (HASH + 1) + c + 1) ? 1 : 0;
  return bits;
}

function distance(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) d += a[i] ^ b[i];
  return d;
}

function capture(video, maxWidth, quality) {
  const scale = Math.min(1, maxWidth / video.videoWidth);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

/** 영상 파일의 길이·크기만 읽는다. */
export async function probe(file) {
  const video = document.createElement("video");
  video.preload = "metadata";
  video.muted = true;
  video.src = URL.createObjectURL(file);
  try {
    await once(video, "loadedmetadata");
    return { duration: video.duration, width: video.videoWidth, height: video.videoHeight, hasVideo: video.videoWidth > 0 };
  } finally {
    URL.revokeObjectURL(video.src);
  }
}

/**
 * 화면이 바뀌는 지점의 키프레임을 고른다.
 * @returns {Promise<Array<{time:number, blob:Blob, diff:number}>>}
 */
export async function extractKeyframes(file, { every = 2, threshold = 10, maxFrames = 40, maxWidth = 1280, quality = 0.8, onProgress } = {}) {
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = URL.createObjectURL(file);
  try {
    await once(video, "loadeddata");
    if (!video.videoWidth) return [];  // 음성만 있는 파일
    const small = document.createElement("canvas");
    small.width = HASH + 1;
    small.height = HASH;
    const ctx = small.getContext("2d", { willReadFrequently: true });
    const duration = video.duration;
    const picked = [];
    let last = null;
    for (let t = 0; t < duration; t += every) {
      await seek(video, Math.min(t, Math.max(duration - 0.1, 0)));
      const h = dhash(video, ctx);
      const diff = last ? distance(h, last) : HASH * HASH;
      if (diff >= threshold) {
        // 화면이 막 바뀌는 중일 수 있으므로 살짝 뒤의 프레임을 뽑는다
        await seek(video, Math.min(t + 0.7, Math.max(duration - 0.1, 0)));
        picked.push({ time: Math.round(t * 10) / 10, blob: await capture(video, maxWidth, quality), diff });
        last = h;
      }
      if (onProgress) onProgress(Math.min(t / duration, 1), picked.length);
    }
    while (picked.length > maxFrames) {  // 상한을 넘으면 변화가 가장 작았던 것부터 버린다 (첫 장은 남긴다)
      let worst = 1;
      for (let i = 2; i < picked.length; i++) if (picked[i].diff < picked[worst].diff) worst = i;
      picked.splice(worst, 1);
    }
    if (onProgress) onProgress(1, picked.length);
    return picked;
  } finally {
    URL.revokeObjectURL(video.src);
  }
}

/**
 * 오디오를 16kHz 모노 MP3로 뽑는다. lamejs가 전역(window.lamejs)에 올라와 있어야 한다.
 * 파일 전체를 메모리에 올려 디코딩하므로 아주 큰 파일(수백 MB 이상)에서는 실패할 수 있다 — 실패하면 null을 돌려준다.
 * @returns {Promise<{blob:Blob, duration:number}|null>}
 */
export async function extractAudio(file, { sampleRate = 16000, kbps = 32, onProgress } = {}) {
  let buffer;
  try {
    // 디코딩하는 쪽의 샘플레이트를 16kHz로 두면 브라우저가 디코딩하면서 바로 줄여 준다
    const ctx = new OfflineAudioContext(1, 1, sampleRate);
    buffer = await ctx.decodeAudioData(await file.arrayBuffer());
  } catch (e) {
    console.warn("오디오 디코딩 실패:", e);
    return null;
  }
  // 모노로 섞는다
  const n = buffer.length;
  const mono = new Float32Array(n);
  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const data = buffer.getChannelData(ch);
    for (let i = 0; i < n; i++) mono[i] += data[i] / buffer.numberOfChannels;
  }
  const encoder = new window.lamejs.Mp3Encoder(1, sampleRate, kbps);
  const parts = [];
  const BLOCK = 1152 * 64;
  const pcm = new Int16Array(BLOCK);
  for (let pos = 0; pos < n; pos += BLOCK) {
    const len = Math.min(BLOCK, n - pos);
    for (let i = 0; i < len; i++) {
      const s = Math.max(-1, Math.min(1, mono[pos + i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    const out = encoder.encodeBuffer(len === BLOCK ? pcm : pcm.subarray(0, len));
    if (out.length) parts.push(new Uint8Array(out));
    if (onProgress) onProgress(Math.min((pos + len) / n, 1));
    await new Promise((r) => setTimeout(r));  // 화면이 멈추지 않게 숨을 돌린다
  }
  const tail = encoder.flush();
  if (tail.length) parts.push(new Uint8Array(tail));
  return { blob: new Blob(parts, { type: "audio/mpeg" }), duration: buffer.duration };
}

/** 백엔드에 작업을 접수한다. 돌려주는 값은 작업 상태(JSON). */
export async function submitJob(apiBase, { audio, frames, duration, title, language = "ko", type = null }) {
  const form = new FormData();
  form.append("consent", "true");
  form.append("meta", JSON.stringify({ duration, title, language, type, frame_times: frames.map((f) => f.time) }));
  if (audio) form.append("audio", audio, "audio.mp3");
  frames.forEach((f, i) => form.append("frames", f.blob, String(i + 1).padStart(4, "0") + ".jpg"));
  const res = await fetch(apiBase.replace(/\/$/, "") + "/api/jobs", { method: "POST", body: form });
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail || "접수 실패 (" + res.status + ")");
  return body;
}
