// مینی‌اپ تیفوسی — همه‌ی داده‌ها از /api ربات، با امضای initData تلگرام
(function () {
  "use strict";
  const hash = new URLSearchParams(location.hash.slice(1));
  const INIT = hash.get("tgWebAppData") || "";

  // پیام به خود تلگرام (همان کار telegram-web-app.js، بدون بار کردنش)
  function tg(eventType, eventData) {
    try {
      if (window.TelegramWebviewProxy && window.TelegramWebviewProxy.postEvent) {
        window.TelegramWebviewProxy.postEvent(eventType, JSON.stringify(eventData || {}));
        return true;
      }
      if (window.parent !== window) {
        window.parent.postMessage(JSON.stringify({ eventType, eventData: eventData || {} }), "*");
        return true;
      }
    } catch (e) {}
    return false;
  }
  try {
    const tp = JSON.parse(hash.get("tgWebAppThemeParams") || "{}");
    if (tp.bg_color) {
      const n = parseInt(tp.bg_color.slice(1), 16);
      const l = 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
      document.documentElement.dataset.theme = l < 128 ? "dark" : "light";
    }
  } catch (e) {}
  // رویدادهایی که تلگرام به صفحه می‌فرسته (همان قرارداد telegram-web-app.js)
  const safe = { top: 0, bottom: 0 }, content = { top: 0, bottom: 0 };
  function applySafe() {
    const r = document.documentElement.style;
    r.setProperty("--tg-top", (safe.top + content.top) + "px");
    r.setProperty("--tg-bottom", (safe.bottom + content.bottom) + "px");
  }
  const onEvent = (type, data) => {
    data = data || {};
    if (type === "safe_area_changed") { safe.top = +data.top || 0; safe.bottom = +data.bottom || 0; applySafe(); }
    else if (type === "content_safe_area_changed") { content.top = +data.top || 0; content.bottom = +data.bottom || 0; applySafe(); }
    else if (type === "home_screen_added") toast("✅ تیفوسی به صفحه‌ی گوشی اضافه شد");
    else if (type === "home_screen_checked" && data.status === "added") document.documentElement.classList.add("on-home");
    else if (type === "fullscreen_failed") document.documentElement.classList.remove("fs");
  };
  window.Telegram = window.Telegram || {};
  window.Telegram.WebView = { receiveEvent: onEvent };
  window.addEventListener("message", (e) => { try { const m = JSON.parse(e.data); if (m && m.eventType) onEvent(m.eventType, m.eventData); } catch (err) {} });

  tg("web_app_ready");
  tg("web_app_expand");
  if (tg("web_app_request_fullscreen")) document.documentElement.classList.add("fs");
  tg("web_app_request_safe_area");
  tg("web_app_request_content_safe_area");
  tg("web_app_check_home_screen");
  tg("web_app_set_header_color", { color: "#050b1f" });
  tg("web_app_set_background_color", { color: "#050b1f" });
  tg("web_app_set_bottom_bar_color", { color: "#050b1f" });

  const I = {
    bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    chat: '<circle cx="12" cy="12" r="9"/><path d="M8 12h.01M12 12h.01M16 12h.01"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14c2.2.6 3.5 2.6 3.5 6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    uplus: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6M19 8v6M16 11h6"/>',
    home: '<path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/>',
    bag: '<path d="M5 8h14l-1 13H6L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    wallet: '<rect x="3" y="6" width="18" height="14" rx="3"/><path d="M16 13h2M3 10h18"/>',
    card: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18M7 15h4"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    back: '<path d="m9 6 6 6-6 6"/>',
    phone: '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z"/><path d="m9 10 3 5 3-5"/>',
    bolt: '<path d="M13 3 5 13h6l-1 8 8-10h-6l1-8Z"/>',
    inf: '<path d="M7 9a3 3 0 1 0 0 6c3 0 7-6 10-6a3 3 0 1 1 0 6c-3 0-7-6-10-6Z"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8M4 13a8 8 0 0 0 14.5 4.5L20 16"/><path d="M4 4v4h4M20 20v-4h-4"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5V14M12 17.5h.01"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/>',
    dotc: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',
    crown: '<path d="M3 8l4 4 5-7 5 7 4-4-2 11H5L3 8Z"/>',
    link: '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>'
  };
  const ic = (n) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${I[n]}</svg>`;
  const n = (v) => Number(v).toLocaleString("en-US");
  const num = (v) => `<span class="num">${v}</span>`;
  const toman = (v) => `${num(n(v))} تومان`;
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const GB = 1073741824;
  const gb = (b) => (b / GB).toFixed(b >= 10 * GB ? 0 : 1);
  const $ = (id) => document.getElementById(id);
  function toast(t) { const e = $("toast"); e.textContent = t; e.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove("show"), 1800); }
  async function copy(text) { try { await navigator.clipboard.writeText(text); toast("کپی شد"); } catch (e) { toast("نگه دار و کپی کن"); } }

  async function api(path, opts) {
    const r = await fetch("api/" + path, Object.assign({ headers: { "X-Init-Data": INIT, "Content-Type": "application/json" } }, opts || {}));
    if (r.status === 401) throw new Error("auth");
    if (r.status === 403) throw new Error("blocked");
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "error");
    return j;
  }

  const S = { me: null, customers: [], stats: { ok: 0, warn: 0, bad: 0 }, shop: [], tab: "home", filt: "all", q: "", kind: null, card: null };
  const TABS = [["home", "home", "خانه"], ["customers", "users", "مشتری‌ها"], ["buy", "bag", "خرید"], ["wallet", "wallet", "کیف پول"], ["card", "card", "کارت سرویس"]];

  function custLine(c) {
    const vol = c.limit ? `${num(gb(c.used))} گیگ از ${num(gb(c.limit))} گیگ` : `نامحدود · ${num(gb(c.used))} گیگ`;
    const left = c.days_left === null ? "بدون انقضا" : c.state === "bad" ? "تمام شده" : `${num(c.days_left)} روز مانده`;
    return `${vol} · ${left}`;
  }
  const V = {
    home: () => `
      <div class="bar"><button class="iconbtn" type="button" data-act="support" aria-label="پشتیبانی">${ic("chat")}</button><button class="pill ghost addhome" type="button" data-act="addhome">${ic("phone")} افزودن به صفحه‌ی گوشی</button></div>
      <div class="herospace" role="img" aria-label="Tifusi"></div>
      <div class="glass wallet"><div class="w"><div class="wicon" aria-hidden="true"></div><div><div class="k">موجودی کیف پول</div><div class="v">${num(n(S.me.balance))}</div></div></div><button class="pill" type="button" data-go="wallet">${ic("refresh")} شارژ کیف پول</button></div>
      <div class="stats">
        <button class="glass tile" type="button" data-f="all">${ic("users")}<b class="num">${S.customers.length}</b><small>مشتری</small></button>
        <button class="glass tile" type="button" data-f="warn">${ic("clock")}<b class="num">${S.stats.warn}</b><small>رو به اتمام</small></button>
        <button class="glass tile" type="button" data-f="bad">${ic("check")}<b class="num">${S.stats.bad}</b><small>تموم شده</small></button>
      </div>
      <button class="cta" type="button" data-goto="buy">${ic("uplus")} ساخت اکانت برای مشتری</button>
      <div class="glass sec"><div class="sech"><b>باید تمدید بشن</b><button type="button" data-f="warn">مشاهده همه</button></div>
        ${S.customers.filter((c) => c.state !== "ok").slice(0, 3).map((c) => `<div class="lrow"><span class="u">${ic("dotc")}${esc(c.username)}</span><span class="d">${c.state === "bad" ? "تمام شده" : `${num(c.days_left)} روز مانده`} <span class="dot ${c.state}"></span></span></div>`).join("") || '<div class="empty">همه‌ی سرویس‌ها سالمن ✓</div>'}
      </div>`,
    customers: () => {
      const q = S.q.toLowerCase();
      const list = S.customers.filter((c) => (S.filt === "all" || (S.filt === "off" ? !c.on : c.state === S.filt)) && c.username.toLowerCase().includes(q));
      const cnt = (k) => (k === "all" ? S.customers.length : k === "off" ? S.customers.filter((c) => !c.on).length : S.stats[k]);
      return `<div class="ptitle"><b>مشتری‌ها</b><small>مدیریت مشتریان و وضعیت سرویس‌ها</small></div>
      <label class="glass search">${ic("search")}<input id="q" type="search" placeholder="جستجوی یوزرنیم…" value="${esc(S.q)}" aria-label="جستجو"></label>
      <div class="filters">${[["all", "همه"], ["warn", "رو به اتمام"], ["bad", "تموم شده"], ["ok", "فعال"], ["off", "خاموش"]].map(([k, l]) => `<button type="button" data-f="${k}" aria-pressed="${k === S.filt}">${l} · ${num(cnt(k))}</button>`).join("")}</div>
      ${list.map((c) => `<div class="glass cust${c.on ? "" : " off"}"><div style="min-width:0"><button type="button" class="nm nmbtn" data-card="${c.id}">${esc(c.username)} ›</button>
        <div class="mt"><span class="dot ${c.on ? c.state : "bad"}"></span><span>${c.on ? custLine(c) : '<span class="offtag">غیرفعال</span>'}</span></div></div>
        <div class="cacts"><button class="pill" type="button" data-send="${c.id}">ارسال</button><button class="pill dark" type="button" data-renew="${c.id}">تمدید</button></div>
        <button class="sw" type="button" role="switch" aria-checked="${c.on}" aria-label="روشن یا خاموش" data-sw="${c.id}"></button></div>`).join("") || '<div class="empty">مشتری‌ای پیدا نشد.</div>'}`;
    },
    buy: () => {
      if (!S.shop.length) return '<div class="empty">فعلاً پلنی برای فروش نیست.</div>';
      const svc = S.shop.find((x) => x.service === S.kind) || S.shop[0];
      S.kind = svc.service;
      return `<div class="ptitle"><b>خرید سرویس</b><small>انتخاب نوع سرویس و پلن مورد نظر</small></div>
      <div class="kinds">${S.shop.map((x) => `<button class="glass kind" type="button" data-kind="${x.service}" aria-pressed="${x.service === S.kind}">${ic(x.service === "xray" ? "shield" : "phone")}<b>${esc(x.label)}</b><small>${x.service === "xray" ? "مخصوص کامپیوتر و سایر دستگاه‌ها" : "مخصوص موبایل و تبلت"}</small></button>`).join("")}</div>
      <div class="h2"><b>پلن‌های ${esc(svc.label)}</b></div>
      <div class="plans">${svc.plans.map((p) => `<button class="glass plan" type="button" data-plan="${p.id}">${ic(p.gb ? "bolt" : "inf")}
        <span class="gb">${p.gb ? `${num(p.gb)} <small>گیگ</small>` : "نامحدود"}</span>${p.gb ? "" : `<span class="dy">${p.users ? `${num(p.users)} کاربره` : "بدون محدودیت"}</span>`}
        <span class="pr">${toman(p.price)}</span><span class="dy">${num(p.days)} روزه</span></button>`).join("")}</div>
      <button class="pill ghost" type="button" data-goto="test" style="justify-content:center">🔑 اکانت تست رایگان</button>`;
    },
    wallet: () => {
      const w = S.wallet;
      if (!w) { loadWallet(); return '<div class="loading">در حال بارگذاری…</div>'; }
      const st = { pending: ["در انتظار تأیید", "warn"], approved: ["تأیید شد", "ok"], rejected: ["رد شد", "bad"] };
      return `<div class="ptitle"><b>کیف پول</b><small>موجودی و شارژ</small></div>
      <div class="glass bigw"><div class="top"><div><div style="color:var(--muted);font-size:.85rem">موجودی کیف پول</div><div class="v">${toman(w.balance)}</div></div><div class="wicon" aria-hidden="true"></div></div></div>
      <div class="amts">${[50000, 100000, 200000, 500000].map((a) => `<button type="button" data-amt="${a}" aria-pressed="${S.amt === a}">${num(a / 1000)} هزار</button>`).join("")}</div>
      <label class="field" for="camt">یا مبلغ دلخواه (تومان)<input id="camt" inputmode="numeric" placeholder="${n(w.min)} تا ${n(w.max)}" value="${S.amt && ![50000, 100000, 200000, 500000].includes(S.amt) ? S.amt : ""}"></label>
      ${w.card_number ? `<div class="glass cardno"><div style="display:flex;justify-content:space-between;color:var(--muted);font-size:.8rem"><span>شماره کارت</span><span>${esc(w.card_name)}</span></div>
        <div class="n"><button type="button" data-copy="${esc(w.card_number.replace(/\D/g, ""))}" aria-label="کپی شماره کارت">${ic("link")}</button><span class="num">${esc(w.card_number)}</span></div></div>`
        : `<div class="glass sec" style="display:grid;gap:10px"><b>💳 شماره کارت</b><p class="soon" style="text-align:right;margin:0">شماره کارت رو از پشتیبانی بگیر؛ پیام بده تا برات بفرستیم.</p>
        <button class="pill ghost" type="button" data-goto="support" style="justify-content:center">💬 گرفتن شماره کارت از پشتیبانی</button></div>`}
      <div class="glass sec" style="display:grid;gap:10px"><b>🧾 ارسال رسید</b>
        <label class="upl" for="rcpt">${ic("refresh")} <span id="rname">انتخاب عکس رسید</span></label><input id="rcpt" type="file" accept="image/*" hidden>
        <button class="cta" type="button" id="csend">ارسال رسید برای تأیید</button>
        <p class="soon" style="margin:0">مبلغ رو بالا انتخاب کن، بعد از واریز عکس رسید رو بفرست. بعد از تأیید ادمین، کیف پولت خودکار شارژ می‌شه و توی چت ربات هم خبرت می‌کنیم.</p></div>
      ${w.receipts.length ? `<div class="glass sec"><div class="sech"><b>رسیدهای اخیر</b></div>${w.receipts.map((r) => `<div class="tx"><span class="ti">${ic("wallet")}</span><div><b>${r.type === "wallet_charge" ? "شارژ کیف پول" : r.type === "purchase" ? "خرید سرویس" : "تمدید"}</b><small class="num">#${r.id}</small></div><span class="am ${(st[r.status] || ["", ""])[1] === "ok" ? "plus" : "minus"}"><span class="num">${n(r.amount)}</span><br><small>${(st[r.status] || [r.status])[0]}</small></span></div>`).join("")}</div>` : ""}`;
    },
    admin: () => {
      const a = S.admin;
      if (!a) { loadAdmin(); return '<div class="loading">در حال بارگذاری…</div>'; }
      const tl = { wallet_charge: "شارژ کیف پول", purchase: "خرید سرویس", renew: "تمدید" };
      return `<div class="ptitle"><b>مدیریت</b><small>فروش و رسیدها</small></div>
      <div class="stats">
        <div class="glass tile">${ic("wallet")}<b class="num">${n(a.span.day.revenue)}</b><small>فروش امروز</small></div>
        <div class="glass tile">${ic("uplus")}<b class="num">${a.span.day.new_users}</b><small>کاربر جدید امروز</small></div>
        <div class="glass tile">${ic("clock")}<b class="num">${a.pending.length}</b><small>رسید در انتظار</small></div>
      </div>
      <div class="glass sec">
        <div class="lrow"><span class="d">فروش ۷ روز</span><span class="v">${toman(a.span.week.revenue)} · ${num(a.span.week.new_orders)} سفارش</span></div>
        <div class="lrow"><span class="d">فروش ۳۰ روز</span><span class="v">${toman(a.span.month.revenue)} · ${num(a.span.month.new_orders)} سفارش</span></div>
        <div class="lrow"><span class="d">سرویس فعال / کاربر</span><span class="v"><span class="num">${a.totals.active}</span> / <span class="num">${a.totals.users}</span></span></div>
        <div class="lrow"><span class="d">تیکت باز</span><span class="v num">${a.totals.tickets_open}</span></div>
      </div>
      <div class="h2"><b>رسیدهای در انتظار</b></div>
      ${a.pending.map((r) => `<div class="glass sec" style="display:grid;gap:10px">
        <div class="sech"><b>${tl[r.type] || r.type} · ${toman(r.amount)}</b><small class="num" style="color:var(--muted)">#${r.id}</small></div>
        <div style="color:var(--muted);font-size:.8rem">${esc(r.user || "")} ${r.uname ? "@" + esc(r.uname) : ""} · <span class="num">${r.user_id}</span>${r.username ? ` · سرویس <span class="num">${esc(r.username)}</span>` : ""}</div>
        <img data-rimg="${r.id}" alt="رسید #${r.id}" style="width:100%;border-radius:14px;background:var(--glass);min-height:120px;object-fit:contain">
        <div class="sacts" style="grid-template-columns:1fr 1fr"><button class="pill" type="button" data-rok="${r.id}" style="justify-content:center;background:linear-gradient(180deg,#6ff0a8,#1fae64)">تأیید</button><button class="pill" type="button" data-rno="${r.id}" style="justify-content:center;background:linear-gradient(180deg,#ff7b7b,#d63a3a);color:#fff">رد</button></div>
      </div>`).join("") || '<div class="empty">رسید در انتظاری نیست ✓</div>'}
      <p class="soon">بقیه‌ی بخش‌های مدیریت فعلاً با دستور /admin توی چت ربات.</p>`;
    },
    card: () => {
      const c = S.customers.find((x) => x.id === S.card) || S.customers[0];
      if (!c) return '<div class="empty">هنوز سرویسی نداری. از تب «خرید» شروع کن.</div>';
      const C = 2 * Math.PI * 50, frac = c.limit ? Math.min(c.used / c.limit, 1) : 1;
      return `<div class="ptitle"><b>کارت سرویس</b><small>اطلاعات و مدیریت سرویس</small></div>
      <div class="glass svc"><div class="svctop">
        <div class="ring"><svg viewBox="0 0 118 118"><circle cx="59" cy="59" r="50" fill="none" stroke="var(--track)" stroke-width="9"/><circle cx="59" cy="59" r="50" fill="none" stroke="${frac > 0.85 && c.limit ? "#f0a43a" : "var(--cyan)"}" stroke-width="9" stroke-linecap="round" stroke-dasharray="${C * frac} ${C}"/></svg>
          <div class="c"><div>${c.limit ? `<b class="num">${gb(Math.max(0, c.limit - c.used))} GB</b><br><small>مونده از ${num(gb(c.limit))} گیگ</small>` : `<b>∞</b><br><small>نامحدود</small>`}</div></div></div>
        <div><h3 style="direction:ltr;text-align:right">${esc(c.username)}</h3><div class="pl">${esc(c.service_name)}</div><div class="chips">${c.service === "xray" ? '<span class="chip">VLESS</span>' : '<span class="chip">IKEv2</span><span class="chip">L2TP</span>'}</div></div></div>
        <div class="days"><span>${c.days_left === null ? "بدون انقضا" : `${num(c.days_left)} روز مانده`}</span></div><div class="dbar"><i style="width:${c.days_left === null ? 100 : Math.min(100, (c.days_left / 30) * 100)}%"></i></div>
        <div class="sacts"><button class="pill" type="button" data-renew="${c.id}">تمدید</button><button class="pill ghost" type="button" data-send="${c.id}">${ic("link")} ارسال</button><button class="pill ghost" type="button" data-guide="${c.id}">${ic("help")} راهنما</button></div></div>
      <div class="glass sec info">
        <div class="lrow"><span class="d">${ic("user")} نام کاربری</span><span class="v">${esc(c.username)}</span></div>
        <div class="lrow"><span class="d">${ic("layers")} سرویس</span><span class="v">${esc(c.service_name)}</span></div>
        <div class="lrow"><span class="d">${ic("check")} وضعیت</span><span style="color:${c.on ? "var(--ok)" : "#ff7b7b"};font-weight:700">${c.on ? "فعال" : "غیرفعال"}</span></div>
      </div>`;
    }
  };

  function render() {
    $("app").innerHTML = V[S.tab]();
    if (S.tab === "admin") loadReceiptImages();
    $("bgart").classList.toggle("dim", S.tab !== "home");
    const tabs = S.me && S.me.is_admin ? TABS.concat([["admin", "crown", "مدیریت"]]) : TABS;
    $("tabs").style.gridTemplateColumns = `repeat(${tabs.length},1fr)`;
    $("tabs").innerHTML = tabs.map(([k, i, l]) => `<button type="button" role="tab" aria-selected="${k === S.tab}" data-tab="${k}">${ic(i)}${l}</button>`).join("");
  }
  function openSend(c) {
    const link = c.guide;
    $("sheet").innerHTML = `<h3 id="sheetTitle">ارسال برای مشتری</h3>
      <p class="soon" style="text-align:right;margin:0">یه صفحه‌ی شخصی برای <b class="num">${esc(c.username)}</b> که وضعیت سرویس، راهنمای اتصال و نصب پروفایل آیفون رو داره.</p>
      ${link ? `<button class="cta" type="button" data-share-tg="${c.id}">ارسال در تلگرام</button>
      <button class="pill ghost" type="button" data-share-wa="${c.id}" style="justify-content:center">ارسال در واتساپ</button>
      <button class="pill ghost" type="button" data-copy="${esc(link)}" style="justify-content:center">${ic("link")} کپی لینک</button>` : '<div class="empty">لینک این سرویس آماده نیست.</div>'}
      <p class="soon">اطلاعات اتصال رو فقط توی تلگرام یا واتساپ بفرست؛ پیام‌رسان‌های داخلی پیام‌ها رو می‌خونن.</p>
      <button class="pill ghost" type="button" data-act="close" style="justify-content:center">بستن</button>`;
    $("sheet").classList.add("open"); $("scrim").classList.add("open");
  }
  async function goto(action, extra) {
    try {
      await api("goto", { method: "POST", body: JSON.stringify(Object.assign({ action }, extra || {})) });
      toast("📩 توی چت ربات ادامه بده");
      setTimeout(() => tg("web_app_close"), 700);
    } catch (e) { toast("الان نشد؛ دوباره امتحان کن"); }
  }
  function openBuy(svc, p) {
    const ipsec = svc.service !== "xray";
    S.buy = { svc, p, qty: 1 };
    const name = p.gb ? `${num(p.gb)} گیگ` : `نامحدود${p.users ? ` ${num(p.users)} کاربره` : ""}`;
    $("sheet").innerHTML = `<h3 id="sheetTitle">خرید ${esc(svc.label)}</h3>
      <div class="sum"><div><span>پلن</span><span>${name} · ${num(p.days)} روزه</span></div><div><span>قیمت هر اکانت</span><span>${toman(p.price)}</span></div><div><span>موجودی</span><span>${toman(S.me.balance)}</span></div></div>
      <label class="field" for="bu">یوزرنیم (خالی بذاری خودش می‌سازه)<input id="bu" autocomplete="off" placeholder="ali12" maxlength="20"></label>
      ${ipsec ? '<label class="field" for="bp">رمز ۶ رقمی (خالی بذاری خودش می‌سازه)<input id="bp" inputmode="numeric" maxlength="6" placeholder="123456"></label>' : ""}
      <div class="stepper"><button class="pill ghost" type="button" data-q="-1" aria-label="کمتر">−</button><output id="bq"></output><button class="pill ghost" type="button" data-q="1" aria-label="بیشتر">+</button></div>
      <p class="soon" id="bnote" style="margin:0"></p>
      <button class="cta" type="button" id="bpay">پرداخت از کیف پول</button>
      <button class="pill ghost" type="button" data-act="close" style="justify-content:center">انصراف</button>`;
    updBuy();
    $("sheet").classList.add("open"); $("scrim").classList.add("open");
  }
  function updBuy() {
    const b = S.buy, total = b.p.price * b.qty, short = total - S.me.balance;
    $("bq").innerHTML = `${num(b.qty)} اکانت · ${toman(total)}`;
    $("bnote").textContent = b.qty > 1 ? "یوزرنیم‌ها پشت سر هم ساخته می‌شن (ali12، ali122، …) و هر کدوم رمز جدا می‌گیره." : "";
    const btn = $("bpay");
    if (short > 0) { btn.textContent = `موجودی کافی نیست (${n(short)} تومان کم داری) · شارژ`; btn.dataset.short = "1"; }
    else { btn.textContent = "پرداخت از کیف پول"; delete btn.dataset.short; }
  }
  async function payBuy() {
    const b = S.buy, btn = $("bpay");
    if (btn.dataset.short) { closeSheet(); S.tab = "wallet"; render(); return; }
    const username = ($("bu").value || "").trim(), password = $("bp") ? ($("bp").value || "").trim() : "";
    if (username && !/^[A-Za-z][A-Za-z0-9_]{2,19}$/.test(username)) { toast("یوزرنیم: با حرف انگلیسی شروع بشه، ۳ تا ۲۰ کاراکتر، فقط حرف و عدد و _"); return; }
    if (password && !/^[0-9۰-۹]{6}$/.test(password)) { toast("رمز باید دقیقاً ۶ رقم باشه"); return; }
    btn.disabled = true; btn.textContent = "در حال ساخت…";
    try {
      const r = await fetch("api/buy", { method: "POST", headers: { "X-Init-Data": INIT, "Content-Type": "application/json" },
        body: JSON.stringify({ service: b.svc.service, plan_id: b.p.id, qty: b.qty, username, password }) });
      const j = await r.json();
      if (!r.ok && !(j.made && j.made.length)) throw Object.assign(new Error(j.error || "error"), { j });
      S.me.balance = j.balance;
      showMade(j.made, j.failed);
      reload();
    } catch (e) {
      btn.disabled = false; updBuy();
      const m = { balance: "موجودی کافی نیست", capacity: "این سرویس الان ظرفیت نداره", username: "یوزرنیم درست نیست", password: "رمز باید ۶ رقم باشه", busy: "یه خرید دیگه در جریانه", plan: "این پلن دیگه فروخته نمی‌شه" }[e.message];
      toast(m || "ساخت نشد؛ پولت برگشت به کیف پول");
    }
  }
  function showMade(made, failed) {
    $("sheet").innerHTML = `<h3 id="sheetTitle">✅ ${num(made.length)} اکانت ساخته شد</h3>
      ${made.map((m) => `<div class="glass cust"><div style="min-width:0"><div class="nm">${esc(m.username)}</div>${m.password ? `<div class="mt">رمز: <span class="num">${esc(m.password)}</span></div>` : ""}</div>
        <div class="cacts">${m.guide ? `<button class="pill" type="button" data-copy="${esc(m.guide)}">کپی لینک</button>` : ""}</div></div>`).join("")}
      ${failed ? `<p class="soon" style="color:#ff9a9a">بقیه ساخته نشد (${esc(failed)})؛ پولش به کیف پول برگشت.</p>` : ""}
      <p class="soon">کارت هر اکانت توی چت ربات هم برات فرستاده شد که بتونی برای مشتری فوروارد کنی.</p>
      <button class="cta" type="button" data-act="close">باشه</button>`;
  }
  async function openRenew(oid) {
    let j;
    try { j = await api("renew_plans?order_id=" + oid); } catch (e) { toast("این سرویس قابل تمدید نیست"); return; }
    S.renew = { order: j.order, plans: j.plans, pick: null };
    $("sheet").innerHTML = `<h3 id="sheetTitle">تمدید ${esc(j.order.username)}</h3>
      <p class="soon" style="text-align:right;margin:0">یه پلن انتخاب کن؛ حجم و زمان از همین لحظه نو می‌شه.</p>
      <div class="plans">${j.plans.map((p) => `<button class="glass plan" type="button" data-rp="${p.id}"><span class="gb">${p.gb ? `${num(p.gb)} <small>گیگ</small>` : "نامحدود"}</span>${p.gb ? "" : `<span class="dy">${p.users ? `${num(p.users)} کاربره` : ""}</span>`}<span class="pr">${toman(p.price)}</span><span class="dy">${num(p.days)} روزه</span></button>`).join("")}</div>
      <div class="sum"><div><span>موجودی</span><span>${toman(S.me.balance)}</span></div></div>
      <button class="cta" type="button" id="rpay" disabled>یه پلن انتخاب کن</button>
      <button class="pill ghost" type="button" data-act="close" style="justify-content:center">انصراف</button>`;
    $("sheet").classList.add("open"); $("scrim").classList.add("open");
  }
  function pickRenew(pid) {
    const r = S.renew; r.pick = r.plans.find((p) => p.id === +pid);
    document.querySelectorAll("[data-rp]").forEach((x) => x.setAttribute("aria-pressed", String(+x.dataset.rp === r.pick.id)));
    const btn = $("rpay"), short = r.pick.price - S.me.balance;
    btn.disabled = false;
    if (short > 0) { btn.textContent = `${n(short)} تومان کم داری · شارژ`; btn.dataset.short = "1"; }
    else { btn.textContent = `تمدید با ${n(r.pick.price)} تومان از کیف پول`; delete btn.dataset.short; }
  }
  async function payRenew() {
    const r = S.renew, btn = $("rpay");
    if (btn.dataset.short) { closeSheet(); S.tab = "wallet"; render(); return; }
    btn.disabled = true; btn.textContent = "در حال تمدید…";
    try {
      const j = await api("renew", { method: "POST", body: JSON.stringify({ order_id: r.order.id, plan_id: r.pick.id }) });
      S.me.balance = j.balance; closeSheet(); toast("✅ " + r.order.username + " تمدید شد"); reload();
    } catch (e) { btn.disabled = false; pickRenew(r.pick.id); toast(e.message === "balance" ? "موجودی کافی نیست" : "تمدید نشد؛ پولت برگشت به کیف پول"); }
  }
  async function loadWallet() {
    try { S.wallet = await api("wallet"); S.me.balance = S.wallet.balance; if (S.tab === "wallet") render(); } catch (e) { toast("الان نشد اطلاعات کیف پول رو بگیرم"); }
  }
  async function sendReceipt() {
    const input = $("rcpt"), btn = $("csend");
    const typed = +String(($("camt") || {}).value || "").replace(/[^0-9۰-۹]/g, "").replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d));
    const amount = typed || S.amt;
    if (!amount || amount < S.wallet.min || amount > S.wallet.max) { toast(`مبلغ باید بین ${n(S.wallet.min)} تا ${n(S.wallet.max)} تومان باشه`); return; }
    if (!input.files || !input.files[0]) { toast("اول عکس رسید رو انتخاب کن"); return; }
    const fd = new FormData(); fd.append("amount", String(amount)); fd.append("photo", input.files[0]);
    btn.disabled = true; btn.textContent = "در حال ارسال…";
    try {
      const r = await fetch("api/charge", { method: "POST", headers: { "X-Init-Data": INIT }, body: fd });
      const j = await r.json(); if (!r.ok) throw new Error(j.error || "error");
      toast("✅ رسید فرستاده شد؛ بعد از تأیید شارژ می‌شه"); S.amt = null; S.wallet = null; render();
    } catch (e) {
      btn.disabled = false; btn.textContent = "ارسال رسید برای تأیید";
      toast({ amount: "مبلغ درست نیست", photo: "عکس رسید رو انتخاب کن", photo_size: "عکس خیلی بزرگه (حداکثر ۸ مگ)" }[e.message] || "ارسال نشد؛ دوباره امتحان کن");
    }
  }
  async function loadAdmin() {
    try { S.admin = await api("admin/summary"); if (S.tab === "admin") render(); } catch (e) { toast("الان نشد اطلاعات مدیریت رو بگیرم"); }
  }
  const imgCache = {};
  async function loadReceiptImages() {
    document.querySelectorAll("[data-rimg]").forEach(async (img) => {
      const id = img.dataset.rimg;
      if (!imgCache[id]) {
        try {
          const r = await fetch("api/admin/receipt_photo?id=" + id, { headers: { "X-Init-Data": INIT } });
          if (!r.ok) return;
          imgCache[id] = URL.createObjectURL(await r.blob());
        } catch (e) { return; }
      }
      img.src = imgCache[id];
    });
  }
  async function decide(id, action, btn) {
    btn.disabled = true;
    try {
      const j = await api("admin/receipt", { method: "POST", body: JSON.stringify({ id: +id, action }) });
      toast(j.status === "approved" ? "✅ تأیید شد" : j.status === "rejected" ? "❌ رد شد" : (j.notes[0] || "انجام شد"));
      S.admin = null; render();
    } catch (e) { btn.disabled = false; toast("انجام نشد؛ دوباره امتحان کن"); }
  }
  async function reload() {
    try {
      const [me, cu] = await Promise.all([api("me"), api("customers")]);
      S.me = me; S.customers = cu.customers; S.stats = cu.stats; render();
    } catch (e) {}
  }
  const closeSheet = () => { $("sheet").classList.remove("open"); $("scrim").classList.remove("open"); };
  const byId = (id) => S.customers.find((c) => c.id === +id);
  function openLink(url) { if (!tg("web_app_open_link", { url })) window.open(url, "_blank"); }

  document.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return; const d = b.dataset;
    if (d.tab) { S.tab = d.tab; render(); scrollTo(0, 0); return; }
    if (d.go) { S.tab = d.go; render(); scrollTo(0, 0); return; }
    if (d.f) { S.filt = d.f; S.tab = "customers"; render(); return; }
    if (d.kind) { S.kind = d.kind; render(); return; }
    if (d.card) { S.card = +d.card; S.tab = "card"; render(); scrollTo(0, 0); return; }
    if (d.send) { const c = byId(d.send); if (c) openSend(c); return; }
    if (d.guide) { const c = byId(d.guide); if (c && c.guide) openLink(c.guide); return; }
    if (d.copy) { copy(d.copy); return; }
    if (d.shareTg) { const c = byId(d.shareTg); const u = `https://t.me/share/url?url=${encodeURIComponent(c.guide)}&text=${encodeURIComponent("اطلاعات اتصال و راهنمای سرویس " + c.username)}`; if (!tg("web_app_open_tg_link", { path_full: u.replace("https://t.me", "") })) openLink(u); return; }
    if (d.shareWa) { const c = byId(d.shareWa); openLink(`https://wa.me/?text=${encodeURIComponent("اطلاعات اتصال و راهنمای سرویس " + c.username + ":\n" + c.guide)}`); return; }
    if (b.id === "bpay") { payBuy(); return; }
    if (d.goto === "buy") { S.tab = "buy"; render(); scrollTo(0, 0); return; }
    if (d.goto) { goto(d.goto); return; }
    if (d.renew) { openRenew(+d.renew); return; }
    if (d.rp) { pickRenew(d.rp); return; }
    if (b.id === "rpay") { payRenew(); return; }
    if (b.id === "csend") { sendReceipt(); return; }
    if (d.rok) { decide(d.rok, "ok", b); return; }
    if (d.rno) { decide(d.rno, "no", b); return; }
    if (d.amt) { S.amt = +d.amt; render(); return; }
    if (d.sw) {
      const c = byId(d.sw); if (!c || b.disabled) return;
      const want = !c.on; b.disabled = true;
      api("toggle", { method: "POST", body: JSON.stringify({ order_id: c.id, on: want }) })
        .then(() => { c.on = want; render(); toast(want ? "✅ " + c.username + " روشن شد" : "⛔ " + c.username + " خاموش شد"); })
        .catch((e) => { b.disabled = false; toast(e.message === "finished" ? "این سرویس تموم شده؛ اول تمدیدش کن" : "الان نشد؛ دوباره امتحان کن"); });
      return;
    }
    if (d.plan) { const svc = S.shop.find((x) => x.service === S.kind); const p = svc && svc.plans.find((x) => x.id === +d.plan); if (p) openBuy(svc, p); return; }
    if (d.q) { S.buy.qty = Math.max(1, Math.min(20, S.buy.qty + +d.q)); updBuy(); return; }
    const a = d.act;
    if (a === "close") closeSheet();
    else if (a === "charge") { S.tab = "wallet"; render(); }
    else if (a === "support") goto("support");
    else if (a === "addhome") { if (!tg("web_app_add_to_home_screen")) toast("از داخل تلگرام روی گوشی باز کن"); }
  });
  document.addEventListener("input", (e) => { if (e.target.id === "q") { S.q = e.target.value; const p = e.target.selectionStart; render(); const x = $("q"); x.focus(); x.setSelectionRange(p, p); } });
  document.addEventListener("change", (e) => { if (e.target.id === "rcpt" && e.target.files[0]) { const l = $("rname"); if (l) l.textContent = "✓ " + e.target.files[0].name; } });
  $("scrim").onclick = closeSheet;

  async function boot() {
    if (!INIT) { $("app").innerHTML = '<div class="empty">این صفحه رو از داخل ربات تلگرام باز کن.</div>'; return; }
    try {
      const [me, cu, pl] = await Promise.all([api("me"), api("customers"), api("plans")]);
      S.me = me; S.customers = cu.customers; S.stats = cu.stats; S.shop = pl.services;
      render();
    } catch (err) {
      $("app").innerHTML = `<div class="empty">${err.message === "blocked" ? "حساب شما مسدود شده است." : err.message === "auth" ? "نشست منقضی شده؛ مینی‌اپ رو ببند و دوباره از ربات باز کن." : "الان نشد اطلاعات رو بگیرم؛ چند لحظه دیگه دوباره امتحان کن."}</div>`;
    }
  }
  boot();
})();
