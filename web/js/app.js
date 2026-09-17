// 화면의 흐름: 올리기 → 만드는 중 → 결과.  작업 ID를 주소의 #job=… 에 두어서, 새로고침해도 결과로 돌아온다.
import { API_BASE } from "./config.js";
import { probe, extractKeyframes, extractAudio, submitJob } from "./preprocess.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");
const mmss = (sec) => {
  sec = Math.floor(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? h + ":" : "") + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
};
const TYPE_LABEL = { meeting: "회의", education: "교육·강의", general: "일반" };

let file = null;      // 사용자가 고른 영상 (이 기기 안에만 있다)
let kind = "";        // 영상 종류 ("" = 자동 판별)
let limits = null;
const SAMPLE_VIDEO = "../samples/lecture-http-caching.mp4";  // 직접 만든 가상 강의 (TTS 음성 + 슬라이드)
let serverReady = null;  // 서버가 깨어나 /api/health에 답하면 풀리는 약속

function show(view) {
  for (const v of ["view-upload", "view-progress", "view-result"]) $(v).hidden = v !== view;
  if (view === "view-progress") startTips();
  window.scrollTo(0, 0);
}

async function api(path, options) {
  let res;
  try {
    res = await fetch(API_BASE + path, options);
  } catch (e) {
    throw new Error("서버에 연결하지 못했습니다. 서버가 잠들어 있으면 깨어나는 데 1분쯤 걸릴 수 있습니다. 잠시 뒤 다시 시도해 주세요.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `요청이 실패했습니다 (${res.status}).`);
  return body;
}

// ── 1. 올리기 ────────────────────────────────────────────────────────────
function refreshStart() {
  $("start").disabled = !(file && $("consent").checked && (!limits || limits.today.left > 0));
}

async function pickFile(f) {
  $("upload-error").hidden = true;
  try {
    const meta = await probe(f);
    if (limits && meta.duration > limits.limits.max_minutes * 60) {
      throw new Error(`영상이 너무 깁니다 (${mmss(meta.duration)}). 지금은 ${limits.limits.max_minutes}분까지 받습니다.`);
    }
    file = f;
    $("drop-title").textContent = f.name;
    $("drop-sub").textContent = `${mmss(meta.duration)} · ${(f.size / 1e6).toFixed(1)}MB${meta.hasVideo ? "" : " · 음성만 있는 파일"}`;
    $("drop").classList.add("picked");
  } catch (e) {
    file = null;
    $("upload-error").textContent = e.message || "이 파일은 읽을 수 없습니다.";
    $("upload-error").hidden = false;
  }
  refreshStart();
}

function initUpload() {
  $("file").addEventListener("change", (e) => e.target.files[0] && pickFile(e.target.files[0]));
  const drop = $("drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && pickFile(e.dataTransfer.files[0]));
  $("kind").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    kind = b.dataset.v;
    document.querySelectorAll("#kind button").forEach((x) => x.classList.toggle("on", x === b));
  });
  $("consent").addEventListener("change", refreshStart);
  $("use-sample").addEventListener("click", async () => {
    const btn = $("use-sample");
    btn.disabled = true;
    btn.textContent = "샘플 영상을 불러오는 중…";
    try {
      const blob = await fetch(SAMPLE_VIDEO).then((r) => { if (!r.ok) throw new Error(); return r.blob(); });
      await pickFile(new File([blob], "샘플 강의 — HTTP 캐싱 기초.mp4", { type: "video/mp4" }));
      $("consent").closest("label").scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {
      $("upload-error").textContent = "샘플 영상을 불러오지 못했습니다.";
      $("upload-error").hidden = false;
    }
    btn.disabled = false;
    btn.textContent = "샘플 강의 영상으로 해 보기 (4분)";
  });
  $("start").addEventListener("click", () => start().catch(fail));

  serverReady = wakeServer();
  serverReady.then((h) => {
    limits = h;
    $("retention").textContent = h.limits.retention_hours;
    $("quota").textContent = h.today.left > 0
      ? `오늘 ${h.today.left}편 더 만들 수 있습니다 (모든 사용자 합쳐 하루 ${h.today.limit}편, ${h.limits.max_minutes}분 이하)`
      : "오늘 만들 수 있는 분량을 다 썼습니다. 내일 다시 찾아 주세요.";
    refreshStart();
  }).catch((e) => { $("quota").textContent = e.message; });
}

// 무료 서버는 한동안 요청이 없으면 잠들고, 깨어나는 데 1분쯤 걸린다. 그동안 화면을 막지 않는다 —
// 영상 고르기와 음성·화면 뽑기는 이 기기에서 하는 일이라 서버 없이도 먼저 해 둘 수 있다.
const WAKE_TIPS = [
  "영상은 이 기기 밖으로 나가지 않아요. 음성과 주요 화면만 뽑아서 보냅니다.",
  "리포트의 모든 문장에는 영상의 몇 분 몇 초인지가 붙어요. 누르면 그 장면으로 갑니다.",
  "퀴즈는 영상에 실제로 나온 내용으로만 만들어요. 지어낸 문제는 없습니다.",
  "슬라이드와 말이 서로 다르면 어느 한쪽 편을 들지 않고 따로 모아 보여 드려요.",
  "퀴즈를 틀리면 영상 전체가 아니라 다시 볼 구간만 알려 드려요.",
  "8컷 만화는 리포트의 핵심만 대화로 풀어낸 요약입니다.",
  "기다리는 동안 영상을 골라 두세요. 서버가 깨어나면 바로 이어집니다.",
];

function wakeServer() {
  const EXPECTED = 60, GIVE_UP = 180;  // 초
  const t0 = Date.now();
  let shown = false, finished = false, tip = 0, timer = null;
  const show = () => {
    shown = true;
    $("wake").hidden = false;
    $("wake-tip").textContent = WAKE_TIPS[0];
    timer = setInterval(() => {
      const sec = (Date.now() - t0) / 1000;
      // 끝을 모르는 기다림이라 막대는 90%까지만 천천히 다가간다
      $("wake-bar").style.width = `${Math.round(90 * (1 - Math.exp(-sec / (EXPECTED / 2))))}%`;
      $("wake-sec").textContent = `${Math.floor(sec)}초째 · 보통 1분 안쪽`;
      if (Math.floor(sec / 6) !== tip) {
        tip = Math.floor(sec / 6);
        const el = $("wake-tip");
        el.classList.add("swap");
        setTimeout(() => { if (!finished) el.textContent = WAKE_TIPS[tip % WAKE_TIPS.length]; el.classList.remove("swap"); }, 250);
      }
    }, 500);
  };
  const delay = setTimeout(show, 1500);  // 깨어 있는 서버는 바로 답하므로 아무것도 띄우지 않는다
  const done = (ok) => {
    finished = true;
    clearTimeout(delay);
    clearInterval(timer);
    if (!shown) return;
    const wake = $("wake");
    if (ok) {
      wake.classList.add("awake");
      $("wake-title").textContent = "서버가 깨어났어요!";
      $("wake-bar").style.width = "100%";
      $("wake-sec").textContent = "";
      $("wake-tip").textContent = "이제 영상을 올리면 바로 만들기 시작합니다.";
      setTimeout(() => { wake.classList.add("leave"); setTimeout(() => { wake.hidden = true; }, 400); }, 1800);
    } else {
      wake.classList.add("failed");
      $("wake-title").textContent = "서버가 일어나지 않네요";
      $("wake-tip").innerHTML = '잠시 뒤 새로고침해 주세요. 그동안 <a href="#demo">완성된 예시</a>는 보실 수 있습니다.';
      $("wake-sec").textContent = "";
    }
  };
  const ask = async () => {
    for (;;) {
      try { return await api("/api/health"); } catch (e) {
        if ((Date.now() - t0) / 1000 > GIVE_UP) throw e;
        await new Promise((r) => setTimeout(r, 4000));
      }
    }
  };
  return ask().then((h) => { done(true); return h; }, (e) => { done(false); throw e; });
}

// ── 2. 만드는 중 ──────────────────────────────────────────────────────────
const LOCAL_STEPS = [["frames", "주요 화면 고르기 (이 기기에서)"], ["audio", "음성 뽑기 (이 기기에서)"], ["send", "서버로 보내기"]];

function renderSteps(local, remote) {
  const row = (label, state, note) =>
    `<li class="${state}"><span class="dot"></span><span class="name">${esc(label)}</span><span class="note">${esc(note || "")}</span></li>`;
  $("steps").innerHTML =
    LOCAL_STEPS.map(([k, label]) => row(label, local[k].state, local[k].note)).join("") +
    (remote || []).map((s) => row(s.label, s.state === "pending" ? "" : s.state, s.state === "failed" ? "실패" : "")).join("");
}

function fail(e) {
  $("progress-error").textContent = e.message || String(e);
  $("progress-error").hidden = false;
  $("progress-actions").hidden = false;
  $("progress-title").textContent = "만들지 못했습니다";
  $("progress-lead").textContent = "";
}

async function start() {
  show("view-progress");
  const local = { frames: { state: "running" }, audio: { state: "" }, send: { state: "" } };
  renderSteps(local);
  const meta = await probe(file);

  const frames = meta.hasVideo
    ? await extractKeyframes(file, { maxFrames: limits ? limits.limits.max_frames : 40,
        onProgress: (p, n) => { local.frames.note = `${Math.round(p * 100)}% · ${n}장`; renderSteps(local); } })
    : [];
  local.frames = { state: "done", note: `${frames.length}장` };
  local.audio.state = "running";
  renderSteps(local);

  const audio = await extractAudio(file, { onProgress: (p) => { local.audio.note = `${Math.round(p * 100)}%`; renderSteps(local); } });
  local.audio = { state: audio ? "done" : "failed", note: audio ? `${(audio.blob.size / 1e6).toFixed(1)}MB` : "음성을 뽑지 못했습니다" };
  if (!audio && !frames.length) throw new Error("이 파일에서 음성도 화면도 읽지 못했습니다. 다른 형식(mp4 권장)으로 바꿔서 다시 시도해 주세요.");
  local.send = { state: "running", note: limits ? "" : "서버가 깨어나는 중…" };
  renderSteps(local, null);
  await serverReady;
  local.send.note = "";
  renderSteps(local);

  const job = await submitJob(API_BASE, { audio: audio && audio.blob, frames, duration: meta.duration,
                                         title: file.name.replace(/\.[^.]+$/, ""), type: kind || null });
  local.send = { state: "done", note: "" };
  history.replaceState(null, "", "#job=" + job.id);
  await follow(job.id, local);
}

async function follow(jobId, local) {
  local = local || { frames: { state: "done" }, audio: { state: "done" }, send: { state: "done" } };
  for (;;) {
    const s = await api("/api/jobs/" + jobId);
    renderSteps(local, s.stages);
    if (s.state === "queued") $("progress-lead").textContent = `앞에 ${Math.max(s.queue_position - 1, 0)}편이 기다리고 있습니다. 한 번에 한 편씩 만듭니다.`;
    if (s.state === "running") $("progress-lead").textContent = "이 창을 닫지 마세요. 영상 길이에 따라 몇 분 걸립니다.";
    if (s.state === "done") return showResult(s);
    if (s.state === "failed") throw new Error(s.error || "알 수 없는 이유로 실패했습니다.");
    await new Promise((r) => setTimeout(r, 4000));
  }
}

// 만드는 동안(1~4분) 서비스가 무엇을 하는지 한 줄씩 보여 준다
let tipTimer = null;
function startTips() {
  if (tipTimer) return;
  let n = 0;
  const el = $("making-tip");
  el.textContent = WAKE_TIPS[0];
  tipTimer = setInterval(() => {
    n += 1;
    el.classList.add("swap");
    setTimeout(() => { el.textContent = WAKE_TIPS[n % (WAKE_TIPS.length - 1)]; el.classList.remove("swap"); }, 250);  // 마지막 팁("영상을 골라 두세요")은 여기서는 맞지 않는다
  }, 7000);
}

// ── 3. 결과 ──────────────────────────────────────────────────────────────
function seekTo(t) {
  const player = $("player");
  if (player.hidden) { $("reselect").classList.add("nudge"); return; }
  player.currentTime = Number(t) || 0;
  player.play();
}

function attachVideo(f) {  // 사용자가 고른 파일, 또는 예시 영상의 주소
  const player = $("player");
  player.src = typeof f === "string" ? f : URL.createObjectURL(f);
  player.hidden = false;
  $("reselect").hidden = true;
  $("seek-hint").hidden = false;
}

function showResult(status, demo = false) {
  show("view-result");
  const base = demo ? "demo/" : `${API_BASE}/api/jobs/${status.id}/files/`;
  $("result-title").textContent = status.title || "리포트";
  $("result-meta").textContent = (TYPE_LABEL[status.type] || "") + (status.failed_parts.length ? " · 일부를 만들지 못했습니다: " + status.failed_parts.join(", ") : "");
  if (demo) {
    $("result-meta").textContent += " · 미리 만들어 둔 예시";
    attachVideo(status.video);
  } else if (file) attachVideo(file);

  const tabs = [];
  if (status.outputs.includes("report")) tabs.push({ key: "report", label: "리포트", src: base + "report.html" });
  if (status.outputs.includes("quiz")) tabs.push({ key: "quiz", label: status.type === "meeting" ? "내용 확인" : "퀴즈" });
  if (status.outputs.includes("comic")) tabs.push({ key: "comic", label: "만화", src: base + "comic.html" });
  $("tabs").innerHTML = tabs.map((t, i) => `<button data-key="${t.key}" class="${i ? "" : "on"}">${t.label}</button>`).join("") +
    (status.outputs.includes("report") ? `<a class="pdf" href="${base}report.html" target="_blank" rel="noopener">리포트 PDF로 저장 ↗</a>` : "");

  if (status.outputs.includes("report")) buildToc(base, () => open("report")).catch(() => {});

  let quizLoaded = false;
  const open = (key) => {
    const tab = tabs.find((t) => t.key === key);
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.key === key));
    $("doc").hidden = key === "quiz";
    $("quiz").hidden = key !== "quiz";
    if (key === "quiz") {
      if (!quizLoaded) { quizLoaded = true; loadQuiz(status, demo).catch((e) => { $("quiz").innerHTML = `<p class="error">${esc(e.message)}</p>`; }); }
    } else if ($("doc").dataset.key !== key) {
      $("doc").dataset.key = key;
      $("doc").src = tab.src;
    }
  };
  $("tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) open(b.dataset.key); };
  if (tabs.length) open(tabs[0].key);
}

// 예시 화면의 채점. 서버의 grade.py와 같은 규칙 — 틀린 문항의 다시 볼 구간을 모으고, 10초 안쪽으로 붙은 구간은 합친다.
function gradeLocally(quiz, answers) {
  const items = quiz.items.map((q) => ({ id: q.id, given: answers[q.id], answer: q.answer, correct: answers[q.id] === q.answer, explanation: q.explanation }));
  const spans = [];
  quiz.items.filter((q, i) => !items[i].correct).map((q) => ({ start: q.review.start, end: q.review.end, items: [q.id] }))
    .sort((a, b) => a.start - b.start).forEach((sp) => {
      const last = spans[spans.length - 1];
      if (last && sp.start <= last.end + 10) { last.end = Math.max(last.end, sp.end); last.items.push(...sp.items); } else spans.push(sp);
    });
  spans.forEach((sp) => { sp.label = `${mmss(sp.start)}–${mmss(sp.end)}`; });
  return { total: items.length, correct: items.filter((r) => r.correct).length, items, review_spans: spans,
           review_seconds: spans.reduce((n, sp) => n + sp.end - sp.start, 0) };
}

// 영상 아래의 목차: 리포트의 섹션과 그 대목이 시작하는 시각. 누르면 영상도 문서도 그리로 간다.
async function buildToc(base, openReport) {
  const report = await fetch(base + "report.json").then((r) => { if (!r.ok) throw new Error(); return r.json(); });
  const rows = [];
  let top = 0;
  for (const sec of report.sections) {
    const times = (sec.items || []).flatMap((it) => (it.timestamps || []).map((t) => t.start));
    if (sec.level === 2) { top += 1; rows.push({ name: sec.heading, section: top, t: times.length ? Math.min(...times) : null, sub: false }); }
    else if (rows.length) {
      rows.push({ name: sec.heading, section: top, t: times.length ? Math.min(...times) : null, sub: true });
    }
  }
  // 하위 제목만 시각을 가진 큰 섹션은 첫 하위 제목의 시각을 물려받는다
  rows.forEach((r, i) => { if (!r.sub && r.t === null) { const k = rows.slice(i + 1).find((x) => x.sub && x.section === r.section && x.t !== null); if (k) r.t = k.t; } });
  if (!rows.length) return;
  const toc = $("toc");
  toc.innerHTML = '<p class="toc-title">목차</p>' + rows.map((r, i) =>
    `<button type="button" class="${r.sub ? "sub" : ""}" data-i="${i}"><span class="name">${esc(r.name)}</span>${r.t === null ? "" : `<span class="t">${mmss(r.t)}</span>`}</button>`).join("");
  toc.hidden = false;
  toc.onclick = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const r = rows[Number(b.dataset.i)];
    openReport();
    const send = () => $("doc").contentWindow.postMessage({ type: "goto", section: r.section }, "*");
    send();
    setTimeout(send, 600);  // 방금 리포트 탭으로 돌아온 경우: 문서가 뜬 뒤 한 번 더
    if (r.t !== null && !$("player").hidden) seekTo(r.t);
  };
}

async function loadQuiz(status, demo) {
  const quiz = demo ? await fetch("demo/quiz.json").then((r) => r.json()) : await api(`/api/jobs/${status.id}/files/quiz.public.json`);
  const meeting = quiz.type === "meeting";
  const answers = {};
  $("quiz").innerHTML =
    `<p class="quiz-lead">${meeting
      ? "점수를 매기는 것이 아니라, 회의에서 정해진 내용을 서로 같게 알고 있는지 확인하는 질문입니다."
      : "영상 내용을 바탕으로 한 질문입니다. 틀린 문항은 다시 볼 구간을 알려 드립니다."}</p>` +
    `<div id="quiz-result" class="quiz-result" hidden></div>` +
    quiz.items.map((q, i) =>
      `<section class="q" id="${q.id}"><h2><span class="num">${i + 1}.</span><span>${md(q.question)}</span></h2>` +
      q.choices.map((c) => `<label class="choice" data-c="${c.id}"><input type="radio" name="${q.id}" value="${c.id}"><span>${md(c.text)}</span><span class="mark"></span></label>`).join("") +
      `<div class="explain"></div></section>`).join("") +
    `<div class="quiz-bar"><span id="quiz-count">0 / ${quiz.items.length} 응답</span><button id="quiz-submit" disabled>제출하기</button></div>`;

  $("quiz").addEventListener("change", (e) => {
    if (e.target.type !== "radio") return;
    answers[e.target.name] = e.target.value;
    e.target.closest(".q").querySelectorAll(".choice").forEach((l) => l.classList.toggle("picked", l.contains(e.target)));
    const n = Object.keys(answers).length;
    $("quiz-count").textContent = `${n} / ${quiz.items.length} 응답`;
    $("quiz-submit").disabled = n < quiz.items.length;
  });

  $("quiz-submit").addEventListener("click", async () => {
    $("quiz-submit").disabled = true;
    let result;
    try {
      result = demo ? gradeLocally(quiz, answers) : await api(`/api/jobs/${status.id}/attempts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }) });
    } catch (e) {
      $("quiz-count").textContent = e.message;
      $("quiz-submit").disabled = false;
      return;
    }
    const spanOf = {};
    result.review_spans.forEach((sp) => sp.items.forEach((id) => { spanOf[id] = sp; }));
    result.items.forEach((row) => {
      const box = $(row.id);
      box.classList.add("done");
      box.querySelectorAll("input").forEach((x) => { x.disabled = true; });
      box.querySelectorAll(".choice").forEach((l) => {
        l.classList.remove("picked");
        if (l.dataset.c === row.answer) { l.classList.add("right"); l.querySelector(".mark").textContent = row.correct ? (meeting ? "맞습니다" : "정답") : (meeting ? "회의에서는 이렇게" : "정답은 이것"); }
        else if (l.dataset.c === row.given) { l.classList.add("wrong"); l.querySelector(".mark").textContent = "선택하신 답"; }
      });
      const sp = spanOf[row.id];
      box.querySelector(".explain").innerHTML = md(row.explanation) +
        (sp ? `<br><a class="ts" href="#" data-t="${sp.start}">▶ 다시 보기 ${esc(sp.label)}</a>` : "");
    });
    const missed = result.total - result.correct;
    const r = $("quiz-result");
    r.hidden = false;
    r.innerHTML = meeting
      ? (missed ? `<strong>다시 확인하실 부분이 ${missed}곳 있습니다.</strong>` : "<strong>회의 내용을 모두 정확히 알고 계십니다.</strong>")
      : `<strong>${result.total}개 중 ${result.correct}개</strong>를 맞히셨습니다.` +
        (result.review_spans.length
          ? ` 아래 구간(총 ${mmss(result.review_seconds)})만 다시 보시면 됩니다.<div class="spans">` +
            result.review_spans.map((sp) => `<a class="ts" href="#" data-t="${sp.start}">▶ ${esc(sp.label)}</a>`).join("") + "</div>"
          : " 영상 내용을 잘 파악하고 계십니다.");
    document.querySelector(".quiz-bar").hidden = true;
    $("quiz").scrollTo({ top: 0, behavior: "smooth" });
  });
}

function initResult() {
  $("file-again").addEventListener("change", (e) => { if (e.target.files[0]) { file = e.target.files[0]; attachVideo(file); } });
  // 퀴즈 화면의 "다시 보기"와, 안에 끼운 문서(리포트·만화)가 보내는 "이 시각으로" 요청
  document.addEventListener("click", (e) => { const a = e.target.closest("a.ts"); if (a) { e.preventDefault(); seekTo(a.dataset.t); } });
  window.addEventListener("message", (e) => { if (e.source === $("doc").contentWindow && e.data && e.data.type === "seek") seekTo(e.data.t); });
  $("retry").addEventListener("click", () => { history.replaceState(null, "", location.pathname + location.search); location.reload(); });
}

// ── 시작 ─────────────────────────────────────────────────────────────────
initUpload();
initResult();
const jobId = (location.hash.match(/job=([A-Za-z0-9_-]+)/) || [])[1];
if (location.hash === "#demo") {
  fetch("demo/status.json").then((r) => r.json()).then((s) => showResult(s, true)).catch(fail);
} else if (jobId) {
  show("view-progress");
  follow(jobId).catch(fail);
}

// 개발용: ?src=/samples/xxx.mp4 로 열면 그 파일을 고른 것으로 친다 (자동 시험에서 파일 선택 창을 띄울 수 없어서)
const devSrc = new URLSearchParams(location.search).get("src");
if (devSrc) {
  fetch(devSrc).then((r) => r.blob()).then((b) => {
    const f = new File([b], devSrc.split("/").pop(), { type: b.type || "video/mp4" });
    if (!jobId) return pickFile(f);
    file = f;  // 결과 화면을 바로 여는 경우: 영상을 붙여 둔다
    if (!$("view-result").hidden) attachVideo(f);
  });
}

// 같은 탭에서 주소의 #job=… 만 바뀐 경우(결과 링크를 붙여 넣었을 때)에도 그 작업을 연다
// (#how, #upload 같은 화면 안 이동은 그대로 둔다)
window.addEventListener("hashchange", () => { if (/^#(demo$|job=)/.test(location.hash)) location.reload(); });
