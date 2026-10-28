"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const number = n => new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 1}).format(n);
  const gb = bytes => new Intl.NumberFormat('en-US', {maximumFractionDigits: 1}).format(bytes / 1073741824) + ' GB';
  const date = ts => ts ? new Intl.DateTimeFormat('fa-IR', {dateStyle:'medium',timeStyle:'short'}).format(new Date(ts * 1000)) : 'ثبت نشده';
  const text = (id, value) => { $(id).textContent = value; };
  let pending = false;
  async function load() {
    if (pending) return;
    pending = true; $('refresh').disabled = true; $('error').hidden = true;
    try {
      const r = await fetch(location.pathname.replace(/\/$/, '') + '/data', {cache:'no-store',credentials:'omit'});
      if (!r.ok) throw new Error(r.status === 404 ? 'این لینک معتبر نیست یا سرویس دیگر موجود نیست.' : 'دریافت اطلاعات فعلاً ممکن نیست. کمی بعد دوباره تلاش کنید.');
      const d = await r.json();
      text('username',d.username); text('protocol',d.service_name);
      const finished = (d.expire && d.days_left === 0) || (d.limit > 0 && d.used >= d.limit);
      const labels = {active:'اشتراک شما فعال است',disabled:'غیرفعال',expired:'پایان اعتبار',limited:'پایان حجم',on_hold:'در انتظار فعال‌سازی'};
      text('status', finished && d.panel_status === 'active' ? 'پایان اعتبار سرویس' : (labels[d.panel_status] || 'وضعیت نامشخص'));
      $('status').className = 'badge' + (finished || ['expired','limited'].includes(d.panel_status) ? ' bad' : d.panel_status !== 'active' ? ' warn' : '');
      const ratio = d.limit > 0 ? Math.min(100, Math.max(0, (d.limit - d.used) / d.limit * 100)) : 0;
      text('remaining',d.limit > 0 ? gb(Math.max(0,d.limit-d.used)) : 'نامحدود');
      text('volume-note',d.limit > 0 ? number(ratio) + '٪' : 'بدون سقف');
      text('used',gb(d.used)); text('limit',d.limit > 0 ? gb(d.limit) : 'نامحدود');
      $('bar').style.width = ratio + '%'; $('meter').setAttribute('aria-valuenow',String(Math.round(ratio)));
      text('days',d.days_left === null ? 'بدون انقضا' : new Intl.NumberFormat('en-US').format(d.days_left));
      $('days').classList.toggle('unlimited',d.days_left === null);
      $('day-unit').hidden = d.days_left === null;
      text('time-left',d.days_left === null ? 'بدون انقضا' : number(d.days_left) + ' روز');
      const expiry = d.expire ? new Intl.DateTimeFormat('fa-IR', {dateStyle:'medium'}).format(new Date(d.expire*1000)) : 'بدون تاریخ پایان';
      text('expiry',expiry);text('expiry-detail',expiry);
      text('last-seen-short',date(d.last_seen));
      $('remaining').classList.toggle('small-number',$('remaining').textContent.length>10);
      text('last-seen',date(d.last_seen));text('updated','آخرین دریافت اطلاعات: ' + date(d.updated_at));
      $('content').hidden = false;
    } catch (e) {
      $('content').hidden = true;
      text('error',e.message || 'دریافت اطلاعات ممکن نیست.');
      const retry = document.createElement('button'); retry.type='button';retry.textContent='تلاش دوباره';retry.addEventListener('click',load);
      $('error').append(document.createElement('br'),retry);$('error').hidden=false;
    } finally { $('loading').hidden = true; $('refresh').disabled = false; pending = false; }
  }
  $('refresh').addEventListener('click',load);
  load();
})();
