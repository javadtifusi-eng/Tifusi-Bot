'use strict';
// Hands-free turns over the existing authenticated Codex conversation API.
(()=>{
 const el=document.createElement('section');el.id='cxLive';el.hidden=true;el.setAttribute('role','dialog');el.setAttribute('aria-modal','true');el.setAttribute('aria-label','مکالمهٔ صوتی کدکس');
 el.innerHTML='<header><span>Codex · مکالمهٔ صوتی</span><button id="cxlClose" aria-label="پایان مکالمه">×</button></header><main><button id="cxlOrb" aria-label="ارسال صحبت یا قطع پخش"><span class="cxlOrb"></span></button><h2 id="cxlStatus" role="status" aria-live="polite"></h2><p id="cxlHint">بعد از مکث، پیامت ارسال می‌شود.</p><div id="cxlText" dir="auto"></div></main><footer><button id="cxlMute" aria-pressed="false">قطع میکروفن</button><button id="cxlRetry" hidden>تلاش دوباره</button><button id="cxlEnd">پایان</button></footer>';
 document.body.append(el);const q=id=>el.querySelector('#'+id);
 let micEpoch=0;
 let epoch=0,ctx=null,stream=null,recorder=null,source=null,analyser=null,mediaNode=null,timer=null,controller=null,active=false,muted=false,phase='idle',ownJob=null;
 const state=(p,text)=>{phase=p;el.dataset.phase=p;q('cxlStatus').textContent=text;q('cxlRetry').hidden=p!=='error';};
 const suppressedJobs=new Set(),previousSpeak=speak;
 speak=async function(m){if(m?.jobId&&suppressedJobs.has(m.jobId)){suppressedJobs.delete(m.jobId);m.manual=true;return;}return previousSpeak(m);};
 const current=e=>active&&epoch===e&&!controller?.signal.aborted;
 function releaseMic(){micEpoch++;clearInterval(timer);timer=null;if(recorder){recorder.onstop=null;try{if(recorder.state==='recording')recorder.stop();}catch{}recorder=null;}stream?.getTracks().forEach(t=>t.stop());stream=null;mediaNode?.disconnect();mediaNode=null;analyser=null;setAudioMode('playback');}
 function stopSound(){if(source){source.onended=null;try{source.stop();}catch{}source=null;}}
 function failure(e){if(!active||e?.name==='AbortError')return;releaseMic();stopSound();state('error',e?.name==='NotAllowedError'?'اجازهٔ میکروفن داده نشده':e?.name==='NotFoundError'?'میکروفن پیدا نشد':e?.status===401?'برنامه را از تلگرام دوباره باز کن':e?.message||'ارتباط صوتی برقرار نشد؛ دوباره تلاش کن.');}
 const wait=(ms,signal)=>new Promise((resolve,reject)=>{const abort=()=>{clearTimeout(t);reject(new DOMException('Cancelled','AbortError'));};const t=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},ms);signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort();});
 async function request(path,opts={}){return getJSON(path,{...opts,signal:controller.signal});}
 async function listen(e){
  if(!current(e)||muted)return;
  if(recorder)return;
  const capture=++micEpoch;state('starting','در حال روشن‌کردن میکروفن…');
  try{
   setAudioMode('play-and-record');await ctx.resume();
   const mic=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
   if(!current(e)||muted||capture!==micEpoch){mic.getTracks().forEach(t=>t.stop());return;}
   stream=mic;mediaNode=ctx.createMediaStreamSource(mic);analyser=ctx.createAnalyser();analyser.fftSize=1024;mediaNode.connect(analyser);
   const mime=['audio/mp4','audio/webm;codecs=opus','audio/webm'].find(t=>MediaRecorder.isTypeSupported(t));
   const r=new MediaRecorder(mic,mime?{mimeType:mime}:{});recorder=r;const parts=[];let bytes=0,voiced=0,silent=0,spoke=false;const started=performance.now();const samples=new Float32Array(analyser.fftSize);
   r.ondataavailable=ev=>{if(ev.data.size){parts.push(ev.data);bytes+=ev.data.size;if(bytes>8*1024*1024&&r.state==='recording')r.stop();}};
   r.onerror=()=>failure(new Error('ضبط صدا متوقف شد؛ دوباره تلاش کن.'));
   r.onstop=()=>{if(recorder!==r)return;const type=r.mimeType;recorder=null;releaseMic();if(!current(e))return;const blob=new Blob(parts,{type});if(!spoke||blob.size<500){listen(e);return;}submit(blob,e).catch(failure);};
   r.start(200);state('listening','گوش می‌دم…');
   timer=setInterval(()=>{if(!current(e)||r.state!=='recording')return;analyser.getFloatTimeDomainData(samples);let sum=0;for(const n of samples)sum+=n*n;const level=Math.sqrt(sum/samples.length);el.style.setProperty('--voice-level',Math.min(level*5,.22));if(level>.018){voiced+=50;silent=0;if(voiced>=200)spoke=true;}else{silent+=50;if(!spoke)voiced=Math.max(0,voiced-50);}if((spoke&&silent>=650)||performance.now()-started>25000)r.stop();},50);
  }catch(err){if(current(e))failure(err);}
 }
 async function submit(blob,e){
  state('transcribing','دارم حرفت رو می‌نویسم…');
  const stt=await request('/stt',{raw:true,body:blob});if(!current(e))return;
  const text=String(stt.text||'').trim();if(!text)throw new Error('صدایی تشخیص داده نشد؛ دوباره بگو.');q('cxlText').textContent=text;
  state('thinking','کدکس داره جواب می‌ده…');
  const sent=await request('/codex/send',{json:{text,spoken:true}});if(!current(e))return;ownJob=sent.job?.id;if(!ownJob)throw new Error('پیام ارسال نشد.');
  let job=sent.job;const deadline=Date.now()+300000;
  while(current(e)){
   await wait(250,controller.signal);const d=await request('/codex/state');if(!current(e))return;S.data.codex=d;job=d.job;
   if(!job||job.id!==ownJob)throw new Error('گفتگو تغییر کرده؛ مکالمه را دوباره شروع کن.');
   if(job.status==='error')throw new Error('پاسخ کدکس کامل نشد؛ متن گفتگو را بررسی کن.');
   if(job.status!=='running'&&!job.audio_pending)break;
   if(Date.now()>deadline)throw new Error('پاسخ طول کشیده؛ ادامه را در چت ببین.');
  }
  if(!current(e))return;
  ownJob=null;q('cxlText').textContent=job.text||'';state('loading','در حال آماده‌کردن صدا…');
  let response;
  if(job.audio){response=await api('/audio/'+encodeURIComponent(job.audio),{signal:controller.signal});}
  else{response=await api('/tts',{json:{text:job.text},signal:controller.signal});}
  const buffer=await response.arrayBuffer();if(!current(e))return;
  setAudioMode('playback');await ctx.resume();const audio=await ctx.decodeAudioData(buffer);if(!current(e))return;
  source=ctx.createBufferSource();source.buffer=audio;source.connect(ctx.destination);state('speaking','دارم جواب می‌دم…');
  source.onended=()=>{source=null;if(current(e)){if(muted)state('muted','میکروفن خاموشه');else listen(e);}};source.start();
 }
 function close(){
  if(!active)return;active=false;epoch++;controller?.abort();controller=null;releaseMic();stopSound();ctx?.close().catch(()=>{});ctx=null;el.hidden=true;$('#app').inert=false;
  // Any already accepted task keeps its existing lifecycle and history.
  if(ownJob)suppressedJobs.add(ownJob);ownJob=null;refresh('codex',true).then(()=>{render.key=null;render();}).catch(()=>{});
 }
 async function open(){
  if(active)return;
  if(rec||recordingBusy){toast('اول ضبط فعلی را تمام کن');return;}
  if(S.data.codex?.job?.status==='running'){toast('کدکس هنوز مشغول پاسخ قبلیه؛ بعد از پایانش تماس را شروع کن.');return;}
  if(albums.codex?.length||$('#input').value.trim()){toast('اول پیام یا پیوستِ آمادهٔ ارسال را بفرست یا پاک کن.');return;}
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){toast('ضبط صدا در این مرورگر در دسترس نیست.');return;}
  const AC=window.AudioContext||window.webkitAudioContext;if(!AC){toast('پخش صدا در این مرورگر در دسترس نیست.');return;}
  active=true;muted=false;const e=++epoch;controller=new AbortController();
  stopPlayback(true);parkMic();closeSheet();ctx=new AC();ctx.resume().catch(()=>{});el.hidden=false;$('#app').inert=true;q('cxlMute').textContent='قطع میکروفن';q('cxlMute').setAttribute('aria-pressed','false');q('cxlText').textContent='';state('starting','در حال اتصال…');
  q('cxlClose').focus({preventScroll:true});
  try{const d=await request('/codex/state');if(!current(e))return;if(d.job?.status==='running')throw new Error('کدکس مشغوله؛ بعد از پایان پاسخ دوباره تلاش کن.');if(!d.voice_ready)throw new Error('سرویس صوتی آماده نیست.');if(!d.voice)await request('/voice',{json:{tab:'codex',on:true}});if(current(e))await listen(e);}catch(err){if(current(e))failure(err);}
 }
 q('cxlClose').onclick=close;q('cxlEnd').onclick=close;
 q('cxlMute').onclick=()=>{muted=!muted;q('cxlMute').setAttribute('aria-pressed',String(muted));q('cxlMute').textContent=muted?'روشن‌کردن میکروفن':'قطع میکروفن';if(muted&&(phase==='listening'||phase==='starting')){releaseMic();state('muted','میکروفن خاموشه');}else if(!muted&&phase==='muted')listen(epoch);};
 q('cxlRetry').onclick=()=>{close();open();};
 q('cxlOrb').onclick=()=>{if(phase==='speaking'){stopSound();if(!muted)listen(epoch);else state('muted','میکروفن خاموشه');}else if(phase==='listening'&&recorder)recorder.stop();};
 document.addEventListener('click',ev=>{if(S.tab==='codex'&&ev.target.closest('[data-cx="voice-screen"]')){ev.preventDefault();ev.stopImmediatePropagation();open();}},true);
 el.addEventListener('keydown',ev=>{if(ev.key==='Escape'){ev.stopPropagation();close();}if(ev.key==='Tab'){const b=[...el.querySelectorAll('button')].filter(x=>!x.hidden);if(ev.shiftKey&&document.activeElement===b[0]){ev.preventDefault();b.at(-1).focus();}else if(!ev.shiftKey&&document.activeElement===b.at(-1)){ev.preventDefault();b[0].focus();}}});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)close();});window.addEventListener('pagehide',close);
 const priorHome=showAssistantHome;showAssistantHome=function(){close();return priorHome();};
})();
