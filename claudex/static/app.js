"use strict";
const tg = window.Telegram && Telegram.WebApp;
const $ = (s) => document.querySelector(s);
const API = "/claudex/api";
const NAMES = { claude: "Claude", codex: "Codex" };
const S = {
  tab: localStorage.getItem("cx-tab") || "claude",
  data: { claude: null, codex: null },
  msgs: { claude: [], codex: [] },
  seenJob: { claude: null, codex: null },
  poll: { claude: null, codex: null },
  image: null,
};
let audioEl = null;

if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor("#200e16"); tg.setBackgroundColor("#200e16"); if(tg.setBottomBarColor)tg.setBottomBarColor("#200e16"); tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) {} }
// Fullscreen insets belong to the whole workspace, including the home screen.
function syncWorkspaceInsets() {
  const root=document.documentElement;
  const safe=tg?.safeAreaInset||{},content=tg?.contentSafeAreaInset||{};
  root.style.setProperty('--tg-top',Math.max(0,(Number(safe.top)||0)+(Number(content.top)||0))+'px');
  root.style.setProperty('--tg-bottom',Math.max(0,(Number(safe.bottom)||0)+(Number(content.bottom)||0))+'px');
}
if(tg){
  ['safeAreaChanged','contentSafeAreaChanged','fullscreenChanged','viewportChanged'].forEach(ev=>{try{tg.onEvent(ev,syncWorkspaceInsets);}catch{}});
  try{tg.onEvent('fullscreenFailed',()=>{document.documentElement.classList.remove('fs');syncWorkspaceInsets();});}catch{}
  if(tg.isVersionAtLeast?.('8.0')&&tg.requestFullscreen){try{tg.requestFullscreen();document.documentElement.classList.add('fs');}catch{}}
  syncWorkspaceInsets();
}

async function api(path, opts = {}) {
  const headers = { "X-Init-Data": (tg && tg.initData) || "" };
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); opts.method = opts.method || "POST"; }
  if (opts.raw) opts.method = "POST";
  const r = await fetch(API + path, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  if (r.status === 401) { $("#lock").classList.remove("hidden"); throw new Error("unauthorized"); }
  if (!r.ok) { const e = new Error("http " + r.status); e.status = r.status; e.body = await r.json().catch(() => ({})); throw e; }
  return r;
}
const getJSON = async (p, o) => (await api(p, o)).json();

function toast(t) {
  const el = $("#toast"); el.textContent = t; el.classList.remove("hidden");
  clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add("hidden"), 2600);
}
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function md(text) {
  const parts = text.split(/```/);
  return parts.map((p, i) => {
    if (i % 2) return "<pre>" + esc(p.replace(/^[^\n]*\n/, "")) + "</pre>";
    return '<div class="t">' + esc(p).replace(/`([^`\n]+)`/g, '<code class="i">$1</code>').replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>") + "</div>";
  }).join("");
}

/* ---------- رندر ---------- */
function render() {
  const t = S.tab, d = S.data[t], chat = $("#chat");
  document.body.dataset.tab = t;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  const isSsh = t === "ssh";
  ["#chat", ".composer", "#sub"].forEach((q) => $(q).classList.toggle("hidden", isSsh));
  $("#ssh").classList.toggle("hidden", !isSsh);
  ["#btnVoice", "#btnUsage", "#btnModel", "#btnSessions"].forEach((q) => $(q).classList.toggle("hidden", isSsh));
  if (isSsh) { $("#busy").classList.add("hidden"); sshShow(); return; }
  if (d) {
    const cur = d.sessions.find((s) => s.id === d.current);
    $("#subSession").textContent = cur ? cur.title : "جلسه‌ی جدید";
    const m = d.models.find((x) => x.id === d.model);
    $("#subModel").textContent = m ? m.label.split(" — ")[0] : (d.model || "پیش‌فرض");
    $("#btnVoice").classList.toggle("on", d.voice);
    const job = d.job, running = job && job.status === "running";
    $("#busy").classList.toggle("hidden", !running);
    if (running) $("#busyText").textContent = job.progress || "در حال کار با " + NAMES[t] + "…";
  }
  // پولینگ هر ۱.۵ ثانیه render را صدا می‌زند؛ تا پیام‌ها عوض نشده‌اند چت را از نو نساز (وگرنه چشمک می‌زند)
  const msgs = S.msgs[t], last = msgs[msgs.length - 1];
  const key = [t, msgs.length, d && d.voice, last && last.text.length].join("|");
  if (key === render.key) return;
  const fresh = render.key && render.key.split("|").slice(0, 1)[0] === t && msgs.length > +render.key.split("|")[1];
  render.key = key;
  chat.innerHTML = "";
  if (!S.msgs[t].length) {
    chat.innerHTML = '<div class="empty"><div class="big">' + (t === "claude" ? "C" : "X") + "</div><h3>" + NAMES[t] + " روی سرور</h3><div>پیامت را بنویس یا ویس بفرست</div></div>";
  }
  S.msgs[t].forEach((m, i) => { const el = bubble(m, i); if (fresh && i === S.msgs[t].length - 1) el.classList.add("new"); chat.appendChild(el); });
  chat.scrollTop = chat.scrollHeight;
}

function bubble(m, i) {
  const el = document.createElement("div");
  const voiceMode = S.data[S.tab] && S.data[S.tab].voice;
  el.className = "msg " + (m.role === "user" ? "user" : "bot");
  let html = "";
  if (m.role === "bot" && voiceMode && !m.error) {
    html += '<div class="voice' + (m.playing ? " playing" : "") + '"><button class="play" data-i="' + i + '"><svg class="ic-play" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg><svg class="ic-pause" viewBox="0 0 24 24"><path d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg></button><div class="wave"></div></div>';
    html += '<button class="show" data-i="' + i + '">نمایش متن</button><div class="hid hidden">' + md(m.text) + "</div>";
  } else if (m.role === "user" && m.spoken && voiceMode) {
    html += '<div class="t">🎙 پیام صوتی</div>';
  } else {
    html += md(m.text);
  }
  (m.files || []).forEach((f) => { html += '<button class="file" data-fid="' + f.id + '" data-img="' + (f.image ? 1 : 0) + '" data-name="' + esc(f.name) + '">' + (f.image ? "🖼 " : "📎 ") + esc(f.name) + "</button>"; });
  if (m.meta) html += '<div class="meta">' + esc(m.meta) + "</div>";
  el.innerHTML = html;
  return el;
}

$("#chat").addEventListener("click", async (e) => {
  const play = e.target.closest(".play"), show = e.target.closest(".show"), file = e.target.closest(".file");
  if (show) { const h = show.nextElementSibling; h.classList.toggle("hidden"); show.textContent = h.classList.contains("hidden") ? "نمایش متن" : "پنهان کردن متن"; }
  if (play) speak(S.msgs[S.tab][+play.dataset.i]);
  if (file) openFile(file);
});

async function openFile(btn) {
  try {
    const blob = await (await api("/file/" + btn.dataset.fid)).blob();
    const url = URL.createObjectURL(blob);
    if (btn.dataset.img === "1" && !btn.nextElementSibling?.classList.contains("pic")) {
      const img = document.createElement("img"); img.className = "pic"; img.src = url; btn.after(img);
    } else if (btn.dataset.img !== "1") {
      const a = document.createElement("a"); a.href = url; a.download = btn.dataset.name; a.click();
    }
  } catch (err) { toast("فایل باز نشد"); }
}

function paintVoice() {
  document.querySelectorAll(".voice").forEach((box) => {
    const m = S.msgs[S.tab][+box.querySelector(".play").dataset.i];
    box.classList.toggle("playing", !!(m && m.playing));
    box.classList.toggle("loading", !!(m && m.loading));
  });
}
function stopOthers(except) {
  S.msgs[S.tab].forEach((x) => { if (x !== except && x.el && !x.el.paused) x.el.pause(); if (x !== except) x.playing = false; });
}
// یک بار زدن: پخش؛ دوباره زدن: مکث؛ باز هم زدن: ادامه
async function speak(m) {
  try {
    if (m.el && !m.el.paused) { m.el.pause(); return; }
    stopOthers(m);
    if (!m.el) {
      if (!m.audio) {
        m.loading = true; paintVoice();
        const res = m.audioId ? await api("/audio/" + m.audioId) : await api("/tts", { json: { text: m.text } });
        m.audio = URL.createObjectURL(await res.blob());
        m.loading = false;
      }
      m.el = new Audio(m.audio);
      m.el.onplay = () => { m.playing = true; paintVoice(); };
      m.el.onpause = () => { m.playing = false; paintVoice(); };
      m.el.onended = () => { m.playing = false; m.el.currentTime = 0; paintVoice(); };
    }
    await m.el.play();
  } catch (err) { m.playing = false; m.loading = false; paintVoice(); toast("پخش صدا ممکن نشد؛ متن را باز کن"); }
}

/* ---------- وضعیت و polling ---------- */
async function refresh(tab, withHistory) {
  let d = await getJSON("/" + tab + "/state");
  if (withHistory && d.current) d = await getJSON("/" + tab + "/state?history=" + encodeURIComponent(d.current));
  S.data[tab] = d;
  if (withHistory) {
    render.key = null;
    S.msgs[tab] = (d.history || []).map((m) => ({ role: m.role === "user" ? "user" : "bot", text: m.text }));
    if (d.job && d.job.status !== "running") S.seenJob[tab] = d.job.id;
  }
  if (d.job && d.job.status === "running") startPoll(tab);
  return d;
}

function startPoll(tab) {
  if (S.poll[tab]) return;
  S.poll[tab] = setInterval(async () => {
    try {
      const d = await getJSON("/" + tab + "/state");
      S.data[tab] = d;
      const job = d.job;
      if (job && job.status !== "running") {
        clearInterval(S.poll[tab]); S.poll[tab] = null;
        if (S.seenJob[tab] !== job.id) {
          S.seenJob[tab] = job.id;
          S.msgs[tab].push({ role: "bot", text: job.text, files: job.files, audioId: job.audio, error: job.status === "error", meta: NAMES[tab] + (job.seconds ? " · " + job.seconds + " ثانیه" : "") });
          if (S.tab === tab && d.voice && !(job.status === "error")) { render(); speak(S.msgs[tab][S.msgs[tab].length - 1]); return; }
        }
      }
      if (S.tab === tab) render();
    } catch (e) { /* دوباره امتحان می‌شود */ }
  }, 600);
}

/* ---------- ارسال ---------- */
async function sendText(text, spoken) {
  const t = S.tab;
  if (!text && !S.image) return;
  const img = S.image; S.image = null; $("#preview").classList.add("hidden");
  S.msgs[t].push({ role: "user", text: (img ? "🖼 " : "") + (text || "عکس"), spoken });
  $("#input").value = ""; autosize(); render();
  try {
    const r = await getJSON("/" + t + "/send", { json: { text, image: img, spoken } });
    S.data[t].job = r.job; render(); startPoll(t);
  } catch (e) {
    S.msgs[t].pop();
    toast(e.status === 409 ? "هنوز روی پیام قبلی کار می‌کنم" : "ارسال نشد");
    render();
  }
}

const input = $("#input");
function autosize() {
  input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px";
  const has = input.value.trim().length > 0 || S.image;
  $("#btnSend").classList.toggle("hidden", !has); $("#btnMic").classList.toggle("hidden", !!has);
}
input.addEventListener("input", autosize);
$("#btnSend").onclick = () => sendText(input.value.trim(), false);
$("#btnStop").onclick = async () => { await getJSON("/" + S.tab + "/stop", { method: "POST" }); toast("⛔️ متوقف شد"); };

$("#btnAttach").onclick = () => $("#file").click();
$("#file").onchange = async (e) => {
  const f = e.target.files[0]; e.target.value = ""; if (!f) return;
  try {
    const r = await getJSON("/upload", { raw: true, body: f });
    S.image = r.image; $("#previewImg").src = URL.createObjectURL(f); $("#preview").classList.remove("hidden"); autosize();
  } catch (err) { toast("عکس ارسال نشد (فقط JPG/PNG/WebP تا ۱۰ مگابایت)"); }
};
$("#previewX").onclick = () => { S.image = null; $("#preview").classList.add("hidden"); autosize(); };

/* ---------- ضبط ویس ---------- */
let rec = null, micStream = null, micIdle = null;
async function getMic() {
  // اجازه‌ی میکروفون فقط یک بار در هر بار باز شدن برنامه پرسیده شود: جریان را نگه می‌داریم و بین ضبط‌ها فقط خاموشش می‌کنیم
  clearTimeout(micIdle);
  if (!micStream || !micStream.getAudioTracks().some((t) => t.readyState === "live")) {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: { ideal: 1 } } });
  }
  micStream.getAudioTracks().forEach((t) => (t.enabled = true));
  return micStream;
}
function parkMic() {
  if (!micStream) return;
  micStream.getAudioTracks().forEach((t) => (t.enabled = false));
  clearTimeout(micIdle);
  micIdle = setTimeout(() => { micStream && micStream.getTracks().forEach((t) => t.stop()); micStream = null; }, 10 * 60 * 1000);
}
// ---- نمایشگر زنده‌ی صدا هنگام ضبط (اکولایزر) ----
const meter = { ctx: null, an: null, src: null, sid: null, raf: 0, levels: [], t0: 0, quiet: 0 };
const BARS = 36;
function startMeter(stream) {
  const viz = $("#recViz");
  if (viz.childElementCount !== BARS) viz.innerHTML = "<i></i>".repeat(BARS);
  $("#row").classList.add("recording"); $("#recBar").classList.remove("hidden"); $("#recHint").classList.add("hidden");
  meter.levels = new Array(BARS).fill(0); meter.t0 = Date.now(); meter.quiet = 0;
  const AC = window.AudioContext || window.webkitAudioContext;
  try {
    if (AC) {
      meter.ctx = meter.ctx || new AC(); meter.ctx.resume();
      if (meter.sid !== stream.id) { meter.src = meter.ctx.createMediaStreamSource(stream); meter.an = meter.ctx.createAnalyser(); meter.an.fftSize = 512; meter.src.connect(meter.an); meter.sid = stream.id; }
    }
  } catch (e) { meter.an = null; }
  const buf = new Uint8Array(512), bars = viz.children;
  const tick = () => {
    const secs = Math.floor((Date.now() - meter.t0) / 1000);
    $("#recTime").textContent = Math.floor(secs / 60) + ":" + String(secs % 60).padStart(2, "0");
    let lvl = 0;
    if (meter.an) {
      meter.an.getByteTimeDomainData(buf);
      let sum = 0; for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
      lvl = Math.min(1, Math.sqrt(sum / buf.length) * 5);
    } else { lvl = 0.25 + 0.2 * Math.sin(Date.now() / 120); }
    meter.levels.push(lvl); meter.levels.shift();
    for (let i = 0; i < BARS; i++) bars[i].style.height = Math.max(3, Math.round(meter.levels[i] * 30)) + "px";
    meter.quiet = lvl < 0.03 ? meter.quiet + 1 : 0;
    $("#recHint").classList.toggle("hidden", !(meter.an && meter.quiet > 90));
    meter.raf = requestAnimationFrame(tick);
  };
  cancelAnimationFrame(meter.raf); tick();
}
function stopMeter() {
  cancelAnimationFrame(meter.raf);
  $("#row").classList.remove("recording"); $("#recBar").classList.add("hidden");
  if (meter.ctx) meter.ctx.suspend().catch(() => {});
}
$("#recCancel").onclick = () => { if (rec) { rec.cancelled = true; rec.stop(); } };

$("#btnMic").onclick = async () => {
  if (rec) { rec.stop(); return; }
  if (!S.data[S.tab].voice_ready) return toast("سرویس صوتی آماده نیست");
  // اگر ویسی در حال پخش است، خودکار قطع شود تا ضبط شروع شود
  Object.values(S.msgs).flat().forEach((x) => { if (x.el && !x.el.paused) x.el.pause(); });
  try {
    const stream = await getMic();
    const mime = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"].find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
    const chunks = [], mr = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
    rec = mr; $("#btnMic").classList.add("rec"); startMeter(stream);
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      parkMic(); stopMeter(); rec = null; $("#btnMic").classList.remove("rec");
      if (mr.cancelled) return toast("ضبط لغو شد");
      const blob = new Blob(chunks, { type: mr.mimeType });
      if (blob.size < 1500) return toast("ویس خیلی کوتاه بود");
      toast("🎙 در حال شنیدن…");
      try {
        const r = await getJSON("/stt", { raw: true, body: blob });
        const spoken = S.data[S.tab].voice;
        sendText(r.text, spoken);
      } catch (e) { toast("ویس خوانده نشد؛ دوباره بفرست یا بنویس"); }
    };
    mr.start();
    setTimeout(() => rec && rec.state === "recording" && rec.stop(), 170000);
  } catch (e) { toast("دسترسی به میکروفون داده نشد"); }
};

/* ---------- شیت‌ها ---------- */
function sheet(html) { $("#sheetContent").innerHTML = html; $("#sheet").classList.remove("hidden"); }
function closeSheet() { $("#sheet").classList.add("hidden"); }
$(".sheet-bg").onclick = closeSheet;

$("#btnSessions").onclick = () => {
  const t = S.tab, d = S.data[t];
  let h = "<h3>🗂 جلسه‌های " + NAMES[t] + " (" + d.sessions.length + ")</h3>";
  d.sessions.forEach((s) => { h += '<div class="item' + (s.id === d.current ? " on" : "") + '" data-open="' + s.id + '"><div class="tt">' + esc(s.title || "بدون عنوان") + "</div><button class=\"del\" data-del=\"" + s.id + '">🗑</button></div>'; });
  if (!d.sessions.length) h += '<div class="empty">هنوز جلسه‌ای نیست</div>';
  h += '<div class="btns"><button class="btn" id="sNew">✨ جلسه‌ی جدید</button>' + (d.sessions.length ? '<button class="btn danger" id="sAll">حذف همه</button>' : "") + "</div>";
  sheet(h);
};
async function sessionAction(json) {
  const t = S.tab;
  S.data[t] = { ...S.data[t], ...(await getJSON("/" + t + "/session", { json })) };
  await refresh(t, true); render();
}
$("#sheetContent").addEventListener("click", async (e) => {
  const t = S.tab, d = S.data[t];
  const del = e.target.closest("[data-del]"), open = e.target.closest("[data-open]"), mod = e.target.closest("[data-model]");
  try {
    if (del) {
      e.stopPropagation();
      if (!confirm("این جلسه حذف شود؟")) return;
      await sessionAction({ action: "delete", sid: del.dataset.del }); closeSheet(); $("#btnSessions").click();
    } else if (open) { await sessionAction({ action: "open", sid: open.dataset.open }); closeSheet(); }
    else if (e.target.id === "sNew") { await sessionAction({ action: "new" }); closeSheet(); }
    else if (e.target.id === "sAll") { if (confirm("همه‌ی جلسه‌ها حذف شود؟ برگشت ندارد.")) { await sessionAction({ action: "deleteall" }); closeSheet(); } }
    else if (mod) { S.data[t] = { ...d, ...(await getJSON("/" + t + "/model", { json: { model: mod.dataset.model } })) }; closeSheet(); render(); }
    else if (e.target.id === "uRefresh") $("#btnUsage").click();
  } catch (err) { toast("انجام نشد"); }
});

$("#btnModel").onclick = () => {
  const d = S.data[S.tab];
  sheet("<h3>🧠 مدل " + NAMES[S.tab] + "</h3>" + d.models.map((m) => '<button class="item' + (m.id === d.model ? " on" : "") + '" data-model="' + esc(m.id) + '"><div class="tt">' + esc(m.label) + "</div>" + (m.id === d.model ? "✅" : "") + "</button>").join(""));
};

$("#btnUsage").onclick = async () => {
  sheet("<h3>📊 مصرف " + NAMES[S.tab] + '</h3><div class="empty">در حال گرفتن…</div>');
  try {
    const u = await getJSON("/" + S.tab + "/usage");
    let h = "<h3>📊 مصرف " + NAMES[S.tab] + "</h3>";
    if (u.error) h += '<div class="empty">' + esc(u.error) + "</div>";
    (u.items || []).forEach((i) => { h += '<div class="usage"><div class="h"><b>' + i.title + "</b><span>" + i.used + "٪ مصرف · " + (100 - i.used) + '٪ مانده</span></div><div class="bar"><i class="' + (i.used >= 85 ? "hot" : "") + '" style="width:' + i.used + '%"></i></div><small>🔄 ریست: ' + i.left + " دیگر (ساعت " + i.at + " تهران)</small></div>"; });
    if (u.ago !== undefined) h += "<small style='color:var(--dim)'>🕒 از آخرین پاسخ ثبت‌شده، " + u.ago + " دقیقه پیش</small>";
    h += '<div class="btns"><button class="btn ghost" id="uRefresh">🔄 تازه‌سازی</button></div>';
    sheet(h);
  } catch (e) { closeSheet(); toast("مصرف گرفته نشد"); }
};

$("#btnVoice").onclick = async () => {
  const on = !S.data[S.tab].voice;
  try {
    await getJSON("/voice", { json: { on } });
    S.data.claude.voice = S.data.codex.voice = on;
    toast(on ? "🎙 فقط‌ویس روشن شد" : "💬 متن فعال شد"); render();
  } catch (e) { toast("سرویس صوتی آماده نیست"); }
};

document.querySelectorAll(".tabs button").forEach((b) => b.onclick = async () => {
  if (S.tab === b.dataset.tab) return;
  S.tab = b.dataset.tab; localStorage.setItem("cx-tab", S.tab);
  S.image = null; $("#preview").classList.add("hidden");
  render();
  if (S.tab === "ssh") return;
  try { await refresh(S.tab, !S.data[S.tab] || !S.msgs[S.tab].length); } catch (e) {}
  render();
});

document.addEventListener("DOMContentLoaded", async function boot() {
  if (!tg || !tg.initData) { $("#lock").classList.remove("hidden"); return; }
  if (!["claude", "codex", "ssh"].includes(S.tab)) S.tab = "claude";
  render();
  if (S.tab !== "ssh") { try { await refresh(S.tab, true); } catch (e) {} }
  render(); autosize();
});

/* ---------- SSH ---------- */
const SSH = { servers: [], cur: null, term: null, fit: null, ws: null, ctrl: false, ready: false };
const KEYS = { enter: "\r", backspace: "\x7f", esc: "\x1b", tab: "\t", up: "\x1b[A", down: "\x1b[B", right: "\x1b[C", left: "\x1b[D" };

function syncSshViewport() {
  const viewport = window.visualViewport;
  const height = Math.min(innerHeight, viewport ? viewport.height : innerHeight, (tg && tg.viewportHeight) || innerHeight);
  const top = viewport ? viewport.offsetTop : 0;
  document.documentElement.style.setProperty("--ssh-height", height + "px");
  document.documentElement.style.setProperty("--ssh-top", top + "px");
  document.body.classList.toggle("keyboard-open", innerHeight - height > 120 || height < 480);
  requestAnimationFrame(sshFit);
}
window.addEventListener("resize", syncSshViewport);
if (window.visualViewport) {
  visualViewport.addEventListener("resize", syncSshViewport);
  visualViewport.addEventListener("scroll", syncSshViewport);
}
if (tg && tg.onEvent) tg.onEvent("viewportChanged", syncSshViewport);
syncSshViewport();
$("#termKeys").addEventListener("pointerdown", e => e.preventDefault());
$("#termKeys").addEventListener("click", () => {
  const keys = $("#keys"), open = keys.hidden;
  keys.hidden = !open;
  $("#termKeys").setAttribute("aria-expanded", String(open));
  $("#termKeys").setAttribute("aria-label", open ? "بستن کلیدهای کمکی" : "نمایش کلیدهای کمکی");
  $("#termKeys").textContent = open ? "−" : "+";
  requestAnimationFrame(sshFit);
});
$("#termKeyboard").addEventListener("pointerdown", e => e.preventDefault());
$("#termKeyboard").addEventListener("click", () => {
  if (!SSH.term) return;
  if (document.activeElement === SSH.term.textarea) SSH.term.blur();
  else SSH.term.focus();
});


async function sshShow() {
  if (!SSH.term) {
    SSH.term = new Terminal({ fontSize: innerWidth < 500 ? 14 : 15, lineHeight: 1.25, cursorBlink: true, fontFamily: "ui-monospace,Menlo,Consolas,monospace", theme: { background: "#06080c", foreground: "#e6e9f2", cursor: "#60dbab" }, scrollback: 5000, allowProposedApi: true });
    SSH.fit = new FitAddon.FitAddon(); SSH.term.loadAddon(SSH.fit);
    SSH.term.open($("#term"));
    const input = SSH.term.textarea;
    input.setAttribute("inputmode", "text");
    input.setAttribute("autocorrect", "off");
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("autocomplete", "off");
    input.spellcheck = false;
    input.addEventListener("focus", () => {
      syncSshViewport();
      [100, 300, 600].forEach(delay => setTimeout(() => {
        syncSshViewport(); SSH.term.scrollToBottom();
      }, delay));
    });
    SSH.term.onData((d) => {
      // Persian/Arabic numeric keypads should select the same shell menu numbers.
      if (/^[۰-۹٠-٩]+$/.test(d)) d = d.replace(/[۰-۹٠-٩]/g, c => String(c.charCodeAt(0) - (c >= "۰" ? 1776 : 1632)));
      if (SSH.ctrl && d.length === 1) { const c = d.toUpperCase().charCodeAt(0); if (c >= 64 && c <= 95) d = String.fromCharCode(c - 64); SSH.ctrl = false; $("#kCtrl").classList.remove("on"); }
      sshSend(d);
    });
    new ResizeObserver(() => sshFit()).observe($("#term"));
  }
  if (!SSH.servers.length) { try { SSH.servers = (await getJSON("/ssh/servers")).servers; } catch (e) { return; } }
  drawServers(); setTimeout(sshFit, 60);
}
function sshFit() {
  if (!SSH.fit || S.tab !== "ssh") return;
  try { SSH.fit.fit(); if (document.activeElement === SSH.term.textarea) SSH.term.scrollToBottom(); if (SSH.ws && SSH.ws.readyState === 1) SSH.ws.send(JSON.stringify({ t: "resize", cols: SSH.term.cols, rows: SSH.term.rows })); } catch (e) {}
}
function sshSend(d) {
  if (typeof d !== "string") return;
  if (SSH.ws && SSH.ws.readyState === 1) {
    SSH.ws.send(JSON.stringify({ t: "in", d }));
    SSH.term.scrollToBottom();
  }
}

$("#btnPanel").onclick = () => {
  const s = SSH.servers.find((x) => x.link);
  if (!s) return;
  if (tg && tg.openLink) tg.openLink(s.link); else window.open(s.link, "_blank");
};
function drawServers() {
  const bar = $("#srvBar");
  $("#btnPanel").hidden = !SSH.servers.some((x) => x.link);
  bar.innerHTML = SSH.servers.map((s) => '<button class="chip' + (s.id === SSH.cur ? " on" : "") + '" data-srv="' + s.id + '">' + '<span class="server-icon" aria-hidden="true">›_</span><span>' + esc(s.name) + "</span></button>").join("") + '<button class="chip add" data-add="1">+ سرور</button>';
}
$("#srvBar").addEventListener("click", (e) => {
  const c = e.target.closest("[data-srv]");
  if (c) { if (SSH.cur === c.dataset.srv && c.classList.contains("on")) return serverSheet(c.dataset.srv); sshConnect(c.dataset.srv); }
  if (e.target.closest("[data-add]")) serverSheet(null);
});
$("#srvBar").addEventListener("contextmenu", (e) => { const c = e.target.closest("[data-srv]"); if (c) { e.preventDefault(); serverSheet(c.dataset.srv); } });

function sshConnect(id) {
  if (SSH.ws) { try { SSH.ws.close(); } catch (e) {} }
  SSH.cur = id; SSH.term.reset(); drawServers();
  $("#termName").textContent = (SSH.servers.find(s => s.id === id) || {}).name || "TERMINAL";
  $("#termState").textContent = "در حال اتصال";
  $("#termState").dataset.state = "connecting";
  const msg = $("#termMsg"); msg.textContent = "در حال اتصال…"; msg.classList.remove("hidden");
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/claudex/ws/ssh");
  ws.binaryType = "arraybuffer"; SSH.ws = ws;
  ws.onopen = () => { SSH.fit.fit(); ws.send(JSON.stringify({ t: "auth", d: tg.initData, server: id, cols: SSH.term.cols, rows: SSH.term.rows })); };
  ws.onmessage = (e) => {
    if (SSH.ws !== ws) return;
    if (typeof e.data === "string") {
      const m = JSON.parse(e.data);
      if (m.t === "error") { $("#termState").textContent = "خطای اتصال"; $("#termState").dataset.state = "error"; msg.textContent = m.d === "too_many" ? "تعداد اتصال‌های باز زیاد است" : "دسترسی مجاز نیست؛ برنامه را از تلگرام دوباره باز کن"; msg.classList.remove("hidden"); }
      if (m.t === "exit") { $("#termState").textContent = "پایان اتصال"; $("#termState").dataset.state = "closed"; SSH.term.write("\r\n\x1b[90m[اتصال بسته شد]\x1b[0m\r\n"); }
      return;
    }
    $("#termState").textContent = "متصل"; $("#termState").dataset.state = "connected";
    msg.classList.add("hidden"); SSH.term.write(new Uint8Array(e.data));
  };
  ws.onclose = () => { if (SSH.ws === ws) { $("#termState").textContent = "قطع اتصال"; $("#termState").dataset.state = "closed"; msg.textContent = "اتصال قطع شد؛ سرور را دوباره بزن"; if (!SSH.term.buffer.active.length) msg.classList.remove("hidden"); } };
  // Open the keyboard only when the terminal or keyboard button is tapped.
}

$("#keys").addEventListener("pointerdown", e => { if (e.target.closest("button")) e.preventDefault(); });
$("#keys").addEventListener("click", async (e) => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.k === "ctrl") { SSH.ctrl = !SSH.ctrl; b.classList.toggle("on", SSH.ctrl); }
  else if (b.dataset.k === "paste") { try { sshSend(await navigator.clipboard.readText()); } catch (err) { toast("اجازه‌ی دسترسی به کلیپ‌بورد نیست؛ با نگه‌داشتن انگشت روی ترمینال بچسبان"); } }
  else if (b.dataset.k) sshSend(KEYS[b.dataset.k]);
  else if (b.dataset.s) sshSend(b.dataset.s);
  SSH.term.focus();
});

function serverSheet(id) {
  const s = SSH.servers.find((x) => x.id === id) || { name: "", host: "", user: "root", port: 22, tmux: false };
  const local = id === "local";
  if (local) return toast("این سرور ثابت است و تنظیمی ندارد");
  sheet("<h3>" + (id ? "ویرایش سرور" : "سرور جدید") + '</h3>' +
    '<label class="lbl">نام</label><input class="field" id="fName" style="direction:rtl;text-align:right" value="' + esc(s.name) + '">' +
    '<label class="lbl">آدرس (IP یا دامنه)</label><input class="field" id="fHost" value="' + esc(s.host) + '" placeholder="1.2.3.4" autocapitalize="off" autocorrect="off">' +
    '<label class="lbl">کاربر</label><input class="field" id="fUser" value="' + esc(s.user) + '" placeholder="root" autocapitalize="off">' +
    '<label class="lbl">پورت</label><input class="field" id="fPort" inputmode="numeric" value="' + s.port + '">' +
    '<label class="chk"><input type="checkbox" id="fTmux"' + (s.tmux ? " checked" : "") + '> نگه‌داشتن جلسه با tmux (اگر روی سرور باشد)</label>' +
    '<p style="color:var(--dim);font-size:12.5px;margin:0 0 12px">رمز یا کلید ذخیره نمی‌شود؛ ssh از کلیدهای این سرور استفاده می‌کند و اگر رمز بخواهد داخل ترمینال تایپ می‌کنی.</p>' +
    '<div class="btns"><button class="btn" id="fSave">ذخیره</button>' + (id ? '<button class="btn danger" id="fDel">حذف از فهرست</button>' : "") + "</div>");
  $("#fSave").onclick = async () => {
    try {
      const r = await getJSON("/ssh/servers", { json: { id, name: $("#fName").value, host: $("#fHost").value, user: $("#fUser").value, port: $("#fPort").value, tmux: $("#fTmux").checked } });
      SSH.servers = r.servers; drawServers(); closeSheet(); toast("ذخیره شد");
    } catch (e) { toast("اطلاعات سرور درست نیست"); }
  };
  if (id) $("#fDel").onclick = async () => {
    if (!confirm("این سرور از فهرست حذف شود؟ به خود سرور کاری ندارد.")) return;
    SSH.servers = (await getJSON("/ssh/servers/delete", { json: { id } })).servers; if (SSH.cur === id) { SSH.cur = null; if (SSH.ws) SSH.ws.close(); SSH.term.reset(); $("#termMsg").classList.remove("hidden"); $("#termMsg").textContent = "یک سرور را انتخاب کن"; }
    drawServers(); closeSheet();
  };
}

/* Telegram-native shortcut keeps signed Telegram authentication. */
function homeScreenState(status) {
  const button = $("#btnHomeScreen");
  button.dataset.status = status;
  button.disabled = status === "added";
  button.textContent = status === "added" ? "✓ روی صفحهٔ گوشی" : "+ افزودن به صفحهٔ گوشی";
}
function homeScreenHelp() {
  sheet("<h3>افزودن به صفحهٔ گوشی</h3><p>در تلگرامِ گوشی، منوی سه‌نقطهٔ بالای همین مینی‌اپ را باز کن و گزینهٔ Add to Home Screen را بزن. اگر این گزینه نیست، تلگرام را به‌روز کن؛ این قابلیت روی همهٔ دستگاه‌ها در دسترس نیست.</p>");
}
$("#btnHomeScreen").addEventListener("click", () => {
  if (!tg || !tg.initData) return homeScreenHelp();
  if (!tg.isVersionAtLeast || !tg.isVersionAtLeast("8.0") || !tg.addToHomeScreen || $("#btnHomeScreen").dataset.status === "unsupported") return homeScreenHelp();
  try { tg.addToHomeScreen(); } catch (e) { homeScreenHelp(); }
});
if (tg && tg.initData && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0")) {
  if (tg.onEvent) {
    tg.onEvent("homeScreenAdded", () => { homeScreenState("added"); toast("به صفحهٔ گوشی اضافه شد"); });
    tg.onEvent("homeScreenChecked", e => homeScreenState(e.status));
    tg.onEvent("homeScreenFailed", () => homeScreenHelp());
  }
  try { if (tg.checkHomeScreenStatus) tg.checkHomeScreenStatus(homeScreenState); } catch(e) {}
}
