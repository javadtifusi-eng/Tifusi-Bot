"use strict";
/* UI layer over existing transport, recorder helpers and SSH. */
let uiLanguage=localStorage.getItem("clodex-language")||"fa";
let engine=["claude","codex"].includes(S.tab)?S.tab:localStorage.getItem("clodex-engine")||"claude";
if(!['claude','codex'].includes(engine))engine='claude';
let view='home';S.tab=engine;
const previewUrls={claude:null,codex:null};
const drafts={claude:"",codex:""},attachments={claude:null,codex:null},scrolls={claude:null,codex:null};
const pollTimers={},requestBusy={},audioRequests=new WeakMap(),urls=new Set();
let playbackEpoch=0,activeMessage=null,recordingBusy=false;
const words={
send:['ارسال','Send'],record:['ضبط ویس','Record voice'],attach:['پیوست عکس','Attach image'],workspace:["فضای کار شخصی","Personal workspace"],private:["خصوصی · فقط شما","Private · owner only"],
chat:["گفتگو","Chat"],sessions:["جلسه‌ها","Sessions"],usage:["مصرف","Usage"],settings:["تنظیمات","Settings"],
newSession:["جلسهٔ جدید","New session"],message:["پیامت را بنویس…","Write a message…"],welcome:["از کجا شروع کنیم؟","What shall we work on?"],welcomeNote:["متن، عکس یا ویس بفرست؛ کار را از همین‌جا ادامه بده.","Send a message, image or voice note to get started."],
close:["بستن","Close"],cancel:["انصراف","Cancel"],confirm:["تأیید","Confirm"],wait:["در حال بارگیری…","Loading…"],failed:["انجام نشد؛ دوباره امتحان کن","Something went wrong. Try again."],
thinking:["در حال فکر کردن…","Thinking…"],stopped:["درخواست توقف ارسال شد","Stop requested"],busy:["هنوز روی پیام قبلی کار می‌کنم","A task is still running"],
model:["مدل","Model"],voice:["ویس","Voice"],voiceOn:["پاسخ صوتی روشن شد","Voice replies enabled"],voiceOff:["پاسخ متنی فعال شد","Text replies enabled"],
showText:["نمایش متن","Show text"],hideText:["پنهان‌کردن متن","Hide text"],audioLoading:["آماده‌سازی صدا","Preparing audio"],play:["پخش / مکث","Play / pause"],stopAudio:["توقف صدا","Stop audio"],audioError:["صدا آماده نشد؛ دوباره پخش را بزن یا متن را بخوان","Audio unavailable. Retry playback or read the text."],
listening:["در حال تبدیل ویس به متن…","Transcribing voice…"],micError:["میکروفن در دسترس نیست؛ دسترسی مرورگر را بررسی کن","Microphone unavailable. Check browser permissions."],shortVoice:["ویس خیلی کوتاه بود","Recording is too short"],recordCancelled:["ضبط لغو شد","Recording cancelled"],voiceLimit:["ویس حداکثر ۳ دقیقه و ۱۰ مگابایت باشد","Voice limit: 3 minutes / 10 MB"],voiceUnavailable:["سرویس صوتی آماده نیست","Voice service is not ready"],
deleteSession:["این جلسه حذف شود؟","Delete this session?"],deleteAll:["همهٔ جلسه‌ها حذف شوند؟","Delete all sessions?"],noSessions:["هنوز جلسه‌ای نیست","No sessions yet"],clear:["حذف همه","Clear all"],remove:["حذف","Delete"],refresh:["تازه‌سازی","Refresh"],
copy:["کپی شد","Copied"],copyFailed:["کپی ممکن نشد؛ متن را انتخاب کن","Select the text to copy it"],uploadError:["فقط JPG، PNG یا WebP تا ۱۰ مگابایت","Use JPG, PNG or WebP up to 10 MB"],fileError:["فایل باز نشد","Could not open file"],
sshTitle:["سرورهای من","My servers"],sshNote:["یک سرور انتخاب کن و شروع کن","Choose a server to connect"],ready:["آمادهٔ اتصال","Ready to connect"],panel:["باز کردن پنل","Open panel"],install:["افزودن به صفحهٔ گوشی","Add to home screen"],
permissionRoot:["دسترسی کامل با حساب root در Claude مجاز نیست؛ این گزینه را فعال نمی‌کنیم.","Claude cannot use Full access as root. Other modes remain available."],
Normal:["معمولی","Normal"],Warm:["گرم و صمیمی","Warm"],Formal:["رسمی","Formal"],Settings:["تنظیمات","Settings"],Model:["مدل","Model"],Effort:["تلاش","Effort"],Permissions:["مجوزها","Permissions"],Sandboxing:["ایزوله‌سازی","Sandboxing"],Language:["زبان پاسخ","Response language"],Notifications:["اعلان‌ها","Notifications"],Back:["بازگشت","Back"],Confirm:["تأیید","Confirm"],Cancel:["انصراف","Cancel"],Default:["پیش‌فرض","Default"],
"Default Model":["مدل پیش‌فرض","Default Model"],"Reasoning Effort":["سطح فکرکردن","Reasoning Effort"],"Approval Mode":["حالت تأیید","Approval Mode"],"Sandbox Mode":["محدودهٔ دسترسی","Sandbox Mode"],"Conversation Tone":["لحن گفتگو","Conversation Tone"],"Response tone (bot)":["لحن پاسخ","Response tone (bot)"],
Low:["کم","Low"],Medium:["متوسط","Medium"],High:["زیاد","High"],"Extra High":["خیلی زیاد","Extra High"],"Extra high":["خیلی زیاد","Extra high"],Max:["حداکثر","Max"],Ultra:["فوق‌العاده زیاد","Ultra"],English:["انگلیسی","English"],Persian:["فارسی","Persian"],"Auto Detect":["تشخیص خودکار","Auto Detect"],"Auto detect":["تشخیص خودکار","Auto detect"],"Read Only":["فقط خواندن","Read Only"],"Workspace Write":["نوشتن در پوشهٔ کار","Workspace Write"],"Full Access":["دسترسی کامل","Full Access"],"Full access":["دسترسی کامل","Full access"],Manual:["دستی","Manual"],"Accept edits":["تأیید ویرایش‌ها","Accept edits"],Plan:["برنامه‌ریزی","Plan"],"Don't ask":["بدون پرسش","Don't ask"],Auto:["خودکار","Auto"],"Reset to default":["بازنشانی","Reset to default"],"Reset to Default":["بازنشانی","Reset to Default"],"Select Model":["انتخاب مدل","Select Model"],
"Enable Notifications":["فعال‌کردن اعلان‌ها","Enable Notifications"],"Disable Notifications":["غیرفعال‌کردن اعلان‌ها","Disable Notifications"],"Enable notifications":["فعال‌کردن اعلان‌ها","Enable notifications"],"Disable notifications":["غیرفعال‌کردن اعلان‌ها","Disable notifications"]
};
function tr(key){return words[key]?words[key][uiLanguage==="fa"?0:1]:key;}
function localized(text){if(words[text])return tr(text);return String(text).replace(/^(Current Model|Current Effort|Current Language|Current Sandbox|Current Status|Selected|Task Completion|Task completion):\s*/,(s)=>uiLanguage==='fa'?({"Current Model":"مدل فعلی","Current Effort":"تلاش فعلی","Current Language":"زبان فعلی","Current Sandbox":"دسترسی فعلی","Current Status":"وضعیت فعلی","Selected":"انتخاب‌شده","Task Completion":"پایان کار","Task completion":"پایان کار"}[s.split(':')[0]]+": "):s);}
function setNav(){document.body.dataset.view=view;$('#brandTitle').textContent=S.tab==='ssh'?'SSH':NAMES[engine];try{if(tg?.BackButton){if(view==='home')tg.BackButton.hide();else tg.BackButton.show();}}catch{}document.querySelectorAll('.tabs button').forEach(b=>{const on=b.dataset.view===view;b.classList.toggle('on',on);b.setAttribute('aria-selected',String(on));});document.querySelectorAll('[data-engine]').forEach(b=>{b.classList.toggle('on',b.dataset.engine===engine);b.setAttribute('aria-pressed',String(b.dataset.engine===engine));});}
function applyLanguage(){document.documentElement.lang=uiLanguage;document.documentElement.dir=uiLanguage==='fa'?'rtl':'ltr';localStorage.setItem('clodex-language',uiLanguage);document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=tr(e.dataset.i18n));$('#btnLang').textContent=uiLanguage==='fa'?'EN':'فا';$('#input').placeholder=tr('message');$('#sheetClose').ariaLabel=tr('Back');$('#sheetClose').textContent=(uiLanguage==='fa'?'› بازگشت':'‹ Back');$('#workspaceBack').ariaLabel=tr('Back');$('#workspaceBack').textContent=uiLanguage==='fa'?'›':'‹';$('#recCancel').textContent=tr('cancel');$('#btnHomeScreen').title=tr('install');$('#btnHomeScreen').ariaLabel=tr('install');$('#lock b').textContent=uiLanguage==='fa'?'دسترسی مجاز نیست':'Access denied';$('#lock p').textContent=uiLanguage==='fa'?'این برنامه فقط از داخل تلگرام و برای مالک کار می‌کند.':'Open this app from Telegram with the owner account.';for(const [id,key] of [['btnVoice','voice'],['btnModel','model'],['btnSessions','sessions'],['btnUsage','usage'],['btnSettings','settings'],['btnSend','send'],['btnMic','record'],['btnAttach','attach']])$('#'+id).ariaLabel=tr(key);$('#btnStop').textContent=uiLanguage==='fa'?'توقف':'Stop';$('.ssh-heading h1').textContent=tr('sshTitle');$('.ssh-heading p').textContent=tr('sshNote');$('#btnPanel').textContent=tr('panel');$('#recHint').textContent=uiLanguage==='fa'?'صدایی شنیده نمی‌شود':'No sound detected';$('#termKeyboard').ariaLabel=uiLanguage==='fa'?'صفحه‌کلید':'Keyboard';$('#termKeys').ariaLabel=uiLanguage==='fa'?'کلیدهای کمکی':'Extra keys';document.querySelector('[data-k=paste]').textContent=uiLanguage==='fa'?'چسباندن':'Paste';render.key=null;render();}
const originalRender=render;
render=function(){originalRender();$('#brandIcon').src='s/'+(engine==='claude'?'claude.svg':'openai.svg?v=white22');setNav();$('.engine-bar').classList.toggle('hidden',S.tab==='ssh');$('.ai-actions').classList.toggle('hidden',S.tab==='ssh');if(S.tab==='ssh')return;const d=S.data[S.tab];if(d){const cur=d.sessions.find(s=>s.id===d.current);$('#subSession').textContent=cur?cur.title:tr('newSession');$('#btnVoice').title=tr('voice');$('#btnModel').title=tr('model');$('#btnSessions').title=tr('sessions');$('#btnUsage').title=tr('usage');$('#btnSettings').title=tr('settings');if(d.job?.status==='running')$('#busyText').textContent=d.job.progress||tr('thinking');}const empty=$('#chat .empty');if(empty)empty.innerHTML='<div class="big"><img src="s/'+(engine==='claude'?'claude.svg':'openai.svg?v=white22')+'" alt=""></div><h3>'+tr('welcome')+'</h3><p>'+tr('welcomeNote')+'</p>';};
const originalMd=md;
md=function(text){return originalMd(String(text||'')).replace(/<pre>/g,'<pre tabindex="0"><button class="copy-code" type="button" aria-label="Copy"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/></svg></button>');};
bubble=function(m,i){const el=document.createElement('div');el.className='msg '+(m.role==='user'?'user':'bot');let h='';const voice=m.role==='bot'&&!m.error&&S.data[S.tab]?.voice;
if(voice){h+='<div class="voice'+(m.playing?' playing':'')+(m.loading||m.audioPending?' loading':'')+'"><button class="play" data-i="'+i+'" aria-label="'+tr('play')+'"><svg class="ic-play" viewBox="0 0 24 24"><path d="M7 5L17 12L7 19Z"/></svg><svg class="ic-pause" viewBox="0 0 24 24"><path d="M7 6h4v12H7zm6 0h4v12h-4z"/></svg></button><div class="wave"></div><span class="audio-status">'+(m.audioPending?tr('audioLoading'):'')+'</span><button class="stop-audio" data-stop-audio="'+i+'" aria-label="'+tr('stopAudio')+'"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1"/></svg></button></div>';h+='<button class="show" data-i="'+i+'">'+tr('showText')+'</button><div class="hid hidden">'+md(m.text)+'</div>';}else h+=md(m.text);
for(const f of m.files||[])h+='<button class="file" data-fid="'+esc(f.id)+'" data-img="'+(f.image?1:0)+'" data-name="'+esc(f.name)+'">'+esc(f.name)+'</button>';
if(m.meta)h+='<div class="meta">'+esc(m.meta)+'</div>';el.innerHTML=h;return el;};
$('#chat').addEventListener('click',async e=>{const b=e.target.closest('.copy-code'),c=e.target.closest('code.i');if(b||c){const text=c?c.textContent:Array.from(b.parentElement.childNodes).filter(n=>n!==b).map(n=>n.textContent).join('');try{await navigator.clipboard.writeText(text);toast(tr('copy'));}catch{toast(tr('copyFailed'));}}if(e.target.closest('[data-stop-audio]'))stopPlayback(true);if(e.target.closest('[data-start-new]'))await sessionAction({action:'new'});if(e.target.closest('[data-open-settings]'))await openControls('root');const show=e.target.closest('.show');if(show)setTimeout(()=>show.textContent=show.nextElementSibling.classList.contains('hidden')?tr('showText'):tr('hideText'),0);});
function blobUrl(blob){const u=URL.createObjectURL(blob);urls.add(u);return u;}
function stopPlayback(reset=false){playbackEpoch++;for(const m of Object.values(S.msgs).flat()){if(m.el){m.el.pause();if(reset)m.el.currentTime=0;}m.playing=false;m.loading=false;audioRequests.get(m)?.abort();}activeMessage=null;paintVoice();}
stopOthers=function(except){for(const m of Object.values(S.msgs).flat())if(m!==except&&m.el){m.el.pause();m.playing=false;}paintVoice();};
speak=async function(m){if(!m)return;if(m.loading){audioRequests.get(m)?.abort();playbackEpoch++;m.loading=false;m.manual=true;paintVoice();return;}m.manual=true;if(m.el&&!m.el.paused){m.el.pause();return;}const ticket=++playbackEpoch;stopOthers(m);activeMessage=m;try{if(!m.el){m.loading=true;paintVoice();const controller=new AbortController();audioRequests.set(m,controller);if(m.voiceUrl){m.audio=m.voiceUrl;}else{let res;if(m.audioId){try{res=await api('/audio/'+m.audioId,{signal:controller.signal});}catch(e){if(e.status!==404)throw e;m.audioId=null;}}if(!res)res=await api('/tts',{json:{text:m.text},signal:controller.signal});const blob=await res.blob();if(ticket!==playbackEpoch)return;m.audio=blobUrl(blob);}m.el=new Audio(m.audio);m.el.volume=1;m.el.preload='auto';m.el.onloadedmetadata=()=>{if(Number.isFinite(m.el.duration)){m.duration=Math.round(m.el.duration);paintVoice();}};m.el.onplay=()=>{stopOthers(m);m.playing=true;m.loading=false;paintVoice();};m.el.onpause=()=>{m.playing=false;paintVoice();};m.el.onended=()=>{m.playing=false;m.el.currentTime=0;paintVoice();};m.el.onerror=()=>{m.loading=false;m.playing=false;paintVoice();};}if(ticket!==playbackEpoch)return;setAudioMode('playback');m.el.volume=1;await m.el.play();}catch(e){if(e.name!=='AbortError'&&ticket===playbackEpoch)toast(tr('audioError'));}finally{m.loading=false;paintVoice();}};
paintVoice=function(){document.querySelectorAll('.voice').forEach(box=>{const m=S.msgs[S.tab]?.[+box.querySelector('.play').dataset.i];box.classList.toggle('playing',!!m?.playing);box.classList.toggle('loading',!!(m?.loading||m?.audioPending));box.querySelector('.audio-status').textContent=m?.audioPending?tr('audioLoading'):'';});};
refresh=async function(tab,withHistory=false){const d=await getJSON('/'+tab+'/state'+(withHistory&&S.data[tab]?.current?'?history='+encodeURIComponent(S.data[tab].current):''));if(withHistory&&d.current&&!d.history){const hd=await getJSON('/'+tab+'/state?history='+encodeURIComponent(d.current));Object.assign(d,hd);}S.data[tab]=d;if(withHistory){scrolls[tab]=null;S.msgs[tab]=(d.history||[]).map(m=>({role:m.role==='user'?'user':'bot',text:m.text}));render.key=null;}if(d.job){if(d.job.status==='running'||d.job.audio_pending)startPoll(tab);else if(withHistory)S.seenJob[tab]=d.job.id;}return d;};
startPoll=function(tab){if(pollTimers[tab])return;const tick=async()=>{try{const d=await getJSON('/'+tab+'/state');S.data[tab]=d;const j=d.job;if(j&&j.status!=='running'){let m=S.msgs[tab].find(x=>x.jobId===j.id);if(!m&&S.seenJob[tab]!==j.id&&d.current===j.sid){S.seenJob[tab]=j.id;m={role:'bot',text:j.text,files:j.files,audioId:j.audio,audioPending:j.audio_pending,jobId:j.id,error:j.status==='error',meta:NAMES[tab]+' · '+(j.model_label||d.model||'Default')};S.msgs[tab].push(m);render.key=null;}if(m){m.audioId=j.audio;m.audioPending=j.audio_pending;if(j.audio_error)m.audioPending=false;}if(!j.audio_pending){if(m&&j.audio&&d.voice&&S.tab===tab&&!document.hidden&&!m.autoPlayed&&!m.manual){m.autoPlayed=true;render();speak(m);}S.seenJob[tab]=j.id;pollTimers[tab]=null;if(S.tab===tab){render();paintVoice();}return;}}if(S.tab===tab){render();paintVoice();}}catch(e){if(e.status===401){pollTimers[tab]=null;return;}}pollTimers[tab]=setTimeout(tick,400);};pollTimers[tab]=setTimeout(tick,150);};
sendText=async function(text,spoken=false,tab=S.tab,voiceNote=null){
 if(!['claude','codex'].includes(tab))return;
 if(albums[tab].some(x=>x.status==='failed'))return toast(uiLanguage==='fa'?'عکس ناموفق را حذف کن و دوباره انتخاب کن':'Remove failed photos and select them again');
 if(albums[tab].some(x=>x.status==='uploading'))return toast(uiLanguage==='fa'?'صبر کن عکس‌ها بارگذاری شوند':'Wait for photos to upload');
 const selected=albums[tab].filter(x=>x.status==='ready');
 if(['/usage','/voice','/start','/menu'].includes(text.trim())&&!selected.length){const cmd=text.trim();if(S.tab===tab){$('#input').value='';autosize();}if(cmd==='/usage')return $('#btnUsage').click();if(cmd==='/voice')return $('#btnVoice').click();return openControls('root',tab);}
 const image=selected[0]?.id||attachments[tab]||((S.tab===tab)?S.image:null);
 if((!text&&!image)||requestBusy[tab])return;
 if(S.data[tab]?.job?.status==='running')return toast(tr('busy'));
 requestBusy[tab]=true;S.msgs[tab].forEach(m=>m.audioPending=false);
 const caption=text||(uiLanguage==='fa'?'عکس':'Image');
 const msg={role:'user',text:caption,spoken:!!voiceNote||spoken,voiceUrl:voiceNote?blobUrl(voiceNote.blob):null,duration:voiceNote?.duration,photos:selected.map(x=>({url:x.url,name:x.name}))};
 S.msgs[tab].push(msg);forceChatBottom=true;
 if(S.tab===tab){$('#input').value='';S.image=null;$('#preview').classList.add('hidden');autosize();}
 drafts[tab]='';attachments[tab]=null;albums[tab]=[];render();
 let prompt=text;
 if(selected.length>1){prompt+=(prompt?'\n\n':'')+'(CLODEX_ATTACHMENTS: '+selected.slice(1).map(x=>'/root/claudex/inbox/'+x.id).join(' ')+' — این عکس‌ها هم ضمیمهٔ همین پیام‌اند؛ همه را با ابزار تصویر بخوان و همراه عکس اول بررسی کن.)';}
 try{const r=await getJSON('/'+tab+'/send',{json:{text:prompt,image,spoken}});S.data[tab]||={sessions:[],models:[]};S.data[tab].job=r.job;startPoll(tab);}
 catch(e){const n=S.msgs[tab].indexOf(msg);if(n>=0)S.msgs[tab].splice(n,1);drafts[tab]=text;attachments[tab]=image;albums[tab]=selected.concat(albums[tab]);if(S.tab===tab){$('#input').value=text;S.image=image;drawAlbum();autosize();}toast(e.status===409?tr('busy'):tr('failed'));}
 finally{requestBusy[tab]=false;render();}
};

const baseSheet=sheet;
sheet=function(content){baseSheet(content);$('#sheet').setAttribute('role','dialog');$('#sheet').setAttribute('aria-modal','true');$('#sheetClose').focus({preventScroll:true});};
closeSheet=function(){controlsEpoch++;for(const b of document.querySelectorAll('[data-control^="cc:"],[data-control^="confirm:"]'))getJSON('/'+engine+'/controls',{json:{action:'dismiss:'+b.dataset.control.split(':')[1]}}).catch(()=>{});$('#sheet').classList.add('hidden');view=S.tab==='ssh'?'ssh':'chat';setNav();};
$('#sheetClose').onclick=closeSheet;$('.sheet-bg').onclick=closeSheet;document.addEventListener('keydown',e=>{if(e.key==='Escape')closeSheet();});
let controlsEpoch=0;
async function openControls(action='root',tab=engine){const token=++controlsEpoch;view='settings';setNav();sheet('<h3>'+tr('settings')+'</h3><p>'+tr('wait')+'</p>');try{const r=await getJSON('/'+tab+'/controls',{json:{action,ui_language:uiLanguage}});if(token!==controlsEpoch||tab!==engine||view!=='settings'||$('#sheet').classList.contains('hidden'))return;S.data[tab]=r.state;if(r.notice)toast(r.notice.includes('root')?tr('permissionRoot'):localized(r.notice));let h='<h3>'+tr('settings')+' · '+NAMES[tab]+'</h3><div class="control-description">'+esc(uiLanguage==='fa'?(r.text_fa||r.text):r.text)+'</div><div class="control-grid">';for(const row of r.rows||[])h+='<div class="control-row">'+row.map(b=>'<button type="button" data-control="'+esc(b.action)+'" class="'+(/^(confirm:|cc:)/.test(b.action)?'confirm':'')+'">'+esc(localized(b.text))+'</button>').join('')+'</div>';h+='</div>';if(['root','home','cs:settings','settings'].includes(action))h+='<div class="workspace-options"><button data-clean-action="sessions">'+tr('sessions')+'</button><button data-clean-action="usage">'+tr('usage')+'</button><button data-clean-action="voice">'+tr('voice')+' · '+(r.state.voice?(uiLanguage==='fa'?'روشن':'On'):(uiLanguage==='fa'?'خاموش':'Off'))+'</button><button data-clean-action="language">'+(uiLanguage==='fa'?'زبان برنامه · فارسی':'App language · English')+'</button><button data-clean-action="home">'+(uiLanguage==='fa'?'انتخاب دستیار':'Choose assistant')+'</button><button data-clean-action="install">'+tr('install')+'</button></div>';sheet(h);render.key=null;render();}catch(e){if(token===controlsEpoch)sheet('<h3>'+tr('settings')+'</h3><p>'+tr('failed')+'</p>');}}
$('#sheetContent').addEventListener('click',e=>{const b=e.target.closest('[data-control]');if(b){if(b.dataset.control==='home'){closeSheet();return;}b.disabled=true;openControls(b.dataset.control);}});
sessionAction=async function(body){const tab=engine;stopPlayback(true);let r=await getJSON('/'+tab+'/session',{json:body});if(r.confirmation)r=await getJSON('/'+tab+'/session',{json:{...body,confirmation:r.confirmation}});S.data[tab]=r;await refresh(tab,true);render();};
$('#btnSessions').onclick=async()=>{const tab=engine,token=++controlsEpoch;view='sessions';setNav();try{await refresh(tab,false);}catch{}const d=S.data[tab];if(!d||token!==controlsEpoch||tab!==engine||view!=='sessions')return;let h='<h3>'+tr('sessions')+' · '+NAMES[tab]+'</h3>';for(const s of d.sessions)h+='<div class="item'+(s.id===d.current?' on':'')+'" data-session-open="'+esc(s.id)+'"><div class="tt">'+esc(s.title||s.id.slice(0,8))+'</div><button class="del" data-session-delete="'+esc(s.id)+'" aria-label="'+tr('remove')+'">×</button></div>';if(!d.sessions.length)h+='<p>'+tr('noSessions')+'</p>';h+='<div class="btns"><button class="btn" data-session-new>'+tr('newSession')+'</button><button class="btn danger" data-session-clear>'+tr('clear')+'</button></div>';sheet(h);};
$('#sheetContent').addEventListener('click',async e=>{const del=e.target.closest('[data-session-delete]'),open=e.target.closest('[data-session-open]');try{if(del){e.stopPropagation();if(!confirm(tr('deleteSession')))return;await sessionAction({action:'delete',sid:del.dataset.sessionDelete});$('#btnSessions').click();}else if(open){await sessionAction({action:'open',sid:open.dataset.sessionOpen});closeSheet();}else if(e.target.closest('[data-session-new]')){await sessionAction({action:'new'});closeSheet();}else if(e.target.closest('[data-session-clear]')){if(confirm(tr('deleteAll'))){await sessionAction({action:'deleteall'});closeSheet();}}else if(e.target.closest('[data-refresh-usage]'))$('#btnUsage').click();}catch{toast(tr('failed'));}});
$('#btnModel').onclick=()=>openControls('models');$('#btnSettings').onclick=()=>openControls('root');
$('#btnUsage').onclick=async()=>{const token=++controlsEpoch;view='usage';setNav();const tab=engine;sheet('<h3>'+tr('usage')+' · '+NAMES[tab]+'</h3><p>'+tr('wait')+'</p>');try{const r=await getJSON('/'+tab+'/usage');if(engine!==tab||view!=='usage'||token!==controlsEpoch)return;let h='<h3>'+tr('usage')+' · '+NAMES[tab]+'</h3>';if(r.error)h+='<p>'+esc(uiLanguage==='en'?'Usage data is unavailable. Send a message and try again.':r.error)+'</p>';for(const i of r.items||[])h+='<div class="usage"><div class="h"><b>'+esc(uiLanguage==='en'?(String(i.title).includes('هفت')?'Weekly limit':'5-hour limit'):i.title)+'</b><span>'+i.used+'% '+(uiLanguage==='fa'?'مصرف‌شده':'used')+'</span></div><div class="bar"><i style="width:'+Math.max(0,Math.min(100,i.used))+'%"></i></div><small>'+esc(uiLanguage==='en'?String(i.left).replace(/روز/g,'days').replace(/ساعت/g,'hours').replace(/دقیقه/g,'minutes').replace(/ و /g,' and ').replace(/[۰-۹]/g,d=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(d)):i.left)+' · '+esc(i.at)+' '+(uiLanguage==='fa'?'تهران':'Tehran')+'</small></div>';if(r.ago!==undefined)h+='<p>'+(uiLanguage==='fa'?'آخرین داده: '+r.ago+' دقیقه پیش':'Last recorded '+r.ago+' min ago')+'</p>';h+='<button class="btn ghost" data-refresh-usage>'+tr('refresh')+'</button>';sheet(h);}catch{sheet('<p>'+tr('failed')+'</p>');}};
$('#btnVoice').onclick=async()=>{if(!S.data[engine])return;try{const r=await getJSON('/voice',{json:{tab:engine,on:!S.data[engine].voice}});S.data[engine].voice=r.voice;toast(tr(r.voice?'voiceOn':'voiceOff'));render.key=null;render();}catch{toast(tr('voiceUnavailable'));}};
$('#btnStop').onclick=async()=>{await getJSON('/'+engine+'/stop',{method:'POST'});toast(tr('stopped'));};
async function switchWorkspace(nextEngine,nextView='chat'){if(recordingBusy||rec){toast(uiLanguage==='fa'?'اول ضبط یا ارسال ویس را تمام کن':'Finish the voice recording first');return;}if(S.tab!=='ssh'&&view!=='home'){drafts[S.tab]=$('#input').value;attachments[S.tab]=S.image;scrolls[S.tab]=$('#chat').scrollTop;}stopPlayback(false);controlsEpoch++;$('#sheet').classList.add('hidden');engine=nextEngine;view=nextView;S.tab=nextView==='ssh'?'ssh':engine;localStorage.setItem('cx-tab',S.tab);localStorage.setItem('clodex-engine',engine);if(S.tab!=='ssh'){S.image=attachments[engine];if(S.image&&previewUrls[engine])$('#previewImg').src=previewUrls[engine];$('#input').value=drafts[engine];$('#preview').classList.toggle('hidden',!S.image);if(!S.data[engine])try{await refresh(engine,true);}catch{toast(tr('failed'));}}render.key=null;render();autosize();if(S.tab!=='ssh'){const target=scrolls[engine],tab=engine;requestAnimationFrame(()=>{if(S.tab!==tab)return;if(target===null)jumpChatToLatest(false);else $('#chat').scrollTop=target;updateLatestButton();});}if(nextView==='sessions')$('#btnSessions').click();if(nextView==='usage')$('#btnUsage').click();if(nextView==='settings')openControls('root');}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>switchWorkspace(engine,b.dataset.view));document.querySelectorAll('[data-engine]').forEach(b=>b.onclick=()=>switchWorkspace(b.dataset.engine,'chat'));
$('#btnLang').onclick=()=>{uiLanguage=uiLanguage==='fa'?'en':'fa';applyLanguage();if(view==='settings')openControls('root');else if(view==='sessions')$('#btnSessions').click();else if(view==='usage')$('#btnUsage').click();};
$('#file').onchange=async e=>{
 const files=Array.from(e.target.files||[]),tab=engine;e.target.value='';if(!files.length)return;
 if(albums[tab].length+files.length>10)return toast(uiLanguage==='fa'?'حداکثر ۱۰ عکس در هر پیام':'Up to 10 photos per message');
 if(files.some(f=>f.size>10*1024*1024))return toast(tr('uploadError'));
 const items=files.map(f=>({key:++photoSequence,file:f,name:f.name,url:blobUrl(f),status:'uploading'}));albums[tab].push(...items);drawAlbum();
 let next=0;
 async function upload(){while(next<items.length){const item=items[next++];try{const r=await getJSON('/upload',{raw:true,body:item.file});if(!/^[a-f0-9]{16}\.(jpg|png|webp)$/.test(r.image))throw new Error('bad_image');item.id=r.image;item.status='ready';}catch{item.status='failed';toast(tr('uploadError'));}finally{item.file=null;if(engine===tab)drawAlbum();}}}
 await Promise.all([upload(),upload()]);
};
$('#previewX').onclick=()=>{albums[engine]=[];attachments[engine]=null;S.image=null;drawAlbum();};

$('#btnMic').onclick=async()=>{if(rec){rec.stop();return;}if(recordingBusy)return;if(!S.data[engine]?.voice_ready)return toast(tr('voiceUnavailable'));if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)return toast(tr('micError'));const tab=engine;recordingBusy=true;stopPlayback(false);try{const stream=await getMic();const mime=['audio/webm;codecs=opus','audio/mp4','audio/webm'].find(x=>MediaRecorder.isTypeSupported(x));const chunks=[],mr=new MediaRecorder(stream,{...(mime?{mimeType:mime}:{}),audioBitsPerSecond:48000});rec=mr;mr.startedAt=Date.now();recordingBusy=false;$('#btnMic').classList.add('rec');startMeter(stream);let size=0;const timer=setTimeout(()=>{if(rec===mr&&mr.state==='recording')mr.stop();},180000);mr.ondataavailable=e=>{if(e.data.size){size+=e.data.size;chunks.push(e.data);if(size>10*1024*1024){mr.cancelled=true;mr.stop();toast(tr('voiceLimit'));}}};mr.onerror=()=>{mr.cancelled=true;try{mr.stop();}catch{}toast(tr('micError'));};mr.onstop=async()=>{clearTimeout(timer);parkMic();stopMeter();rec=null;$('#btnMic').classList.remove('rec');if(mr.cancelled)return;const blob=new Blob(chunks,{type:mr.mimeType});const recordedDuration=Math.max(1,Math.round((Date.now()-mr.startedAt)/1000));if(blob.size<500)return toast(tr('shortVoice'));recordingBusy=true;$('#btnMic').disabled=true;$('#sttStatusText').textContent=tr('listening');$('#sttStatus').classList.remove('hidden');try{const r=await getJSON('/stt',{raw:true,body:blob});await sendText(r.text,true,tab,{blob,duration:recordedDuration});}catch{toast(tr('failed'));}finally{recordingBusy=false;$('#btnMic').disabled=false;$('#sttStatus').classList.add('hidden');}};mr.start(300);}catch{recordingBusy=false;parkMic();stopMeter();toast(tr('micError'));}};
$('#recCancel').onclick=()=>{if(rec){rec.cancelled=true;rec.stop();toast(tr('recordCancelled'));}};
window.addEventListener('pagehide',e=>{stopPlayback(true);if(rec){rec.cancelled=true;rec.stop();}if(e.persisted){parkMic();return;}micStream?.getTracks().forEach(t=>t.stop());micStream=null;for(const u of urls)URL.revokeObjectURL(u);});
const retainedSsh={"+ سرور":"+ Server","اتصال قطع شد؛ سرور را دوباره بزن":"Connection lost. Select the server to reconnect.","تعداد اتصال‌های باز زیاد است":"Too many open connections","دسترسی مجاز نیست؛ برنامه را از تلگرام دوباره باز کن":"Access denied. Reopen this app from Telegram.","یک سرور را انتخاب کن":"Choose a server","این سرور ثابت است و تنظیمی ندارد":"This built-in server has no editable settings.","اطلاعات سرور درست نیست":"Check the server details.","ذخیره شد":"Saved","افزودن به صفحهٔ گوشی":"Add to home screen","در تلگرامِ گوشی، منوی سه‌نقطهٔ بالای همین مینی‌اپ را باز کن و گزینهٔ Add to Home Screen را بزن. اگر این گزینه نیست، تلگرام را به‌روز کن؛ این قابلیت روی همهٔ دستگاه‌ها در دسترس نیست.":"In Telegram on your phone, open the menu above this app and choose Add to Home Screen. If unavailable, update Telegram. Device support may vary.","سرور جدید":"New server","ویرایش سرور":"Edit server","نام":"Name","آدرس (IP یا دامنه)":"Address (IP or domain)","کاربر":"User","پورت":"Port","ذخیره":"Save","حذف از فهرست":"Remove from list","این سرور":"This server","سرور پنل":"Panel server","در حال اتصال":"Connecting","متصل":"Connected","قطع اتصال":"Disconnected","پایان اتصال":"Connection ended","خطای اتصال":"Connection error","در حال اتصال…":"Connecting…","ترمینال آماده‌ست":"Terminal is ready","برای اتصال، یکی از سرورهای بالا را انتخاب کن":"Choose a server above to connect","آمادهٔ اتصال":"Ready to connect","نگه‌داشتن جلسه با tmux (اگر روی سرور باشد)":"Keep session with tmux (if installed)","رمز یا کلید ذخیره نمی‌شود؛ ssh از کلیدهای این سرور استفاده می‌کند و اگر رمز بخواهد داخل ترمینال تایپ می‌کنی.":"Passwords and keys are not stored here. SSH uses server keys; enter passwords in the terminal if prompted."};
const observer=new MutationObserver(mutations=>{if(uiLanguage!=='en')return;for(const m of mutations)for(const node of m.addedNodes){if(node.nodeType!==1&&node.nodeType!==3)continue;const walker=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);const texts=node.nodeType===3?[node]:[];while(walker.nextNode())texts.push(walker.currentNode);for(const n of texts){if(n.parentElement?.closest('#term,.msg'))continue;const text=n.textContent.trim();if(retainedSsh[text])n.textContent=n.textContent.replace(text,retainedSsh[text]);}}});observer.observe(document.body,{childList:true,subtree:true});
function translateSshTree(){
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 const table=uiLanguage==='en'?retainedSsh:Object.fromEntries(Object.entries(retainedSsh).map(([a,b])=>[b,a]));
 for(const n of nodes){if(n.parentElement?.closest('#term,.msg,script,style'))continue;const text=n.textContent.trim();if(table[text])n.textContent=n.textContent.replace(text,table[text]);}
}
const priorApplyLanguage=applyLanguage;
applyLanguage=function(){priorApplyLanguage();translateSshTree();};
applyLanguage();

// Restore media playback routing after recording; Safari may otherwise keep call audio routing.
function setAudioMode(type){try{if(navigator.audioSession)navigator.audioSession.type=type;}catch{}}
const retainedGetMic=getMic,retainedParkMic=parkMic,retainedStopMeter=stopMeter;
let microphoneRequest=null;
getMic=async function(){
 setAudioMode('play-and-record');
 if(!microphoneRequest)microphoneRequest=retainedGetMic().finally(()=>{microphoneRequest=null;});
 return microphoneRequest;
};
parkMic=function(){retainedParkMic();setAudioMode('playback');};
stopMeter=function(){retainedStopMeter();setAudioMode('playback');};
setAudioMode('playback');

// Minimal workspace: controls stay in Settings; conversations and SSH stay mounted.
function showAssistantHome(){
 if(rec||recordingBusy)return toast(uiLanguage==='fa'?'اول ضبط یا ارسال ویس را تمام کن':'Finish your voice recording first');
 if(S.tab!=='ssh'&&view!=='home'){drafts[S.tab]=$('#input').value;attachments[S.tab]=S.image;scrolls[S.tab]=$('#chat').scrollTop;}
 closeSheet();stopPlayback(false);view='home';setNav();
}
$('#workspaceBack').onclick=showAssistantHome;
document.querySelectorAll('[data-choose-engine]').forEach(b=>b.onclick=()=>switchWorkspace(b.dataset.chooseEngine,'chat'));
$('#sheetContent').addEventListener('click',async e=>{
 const b=e.target.closest('[data-clean-action]');if(!b)return;
 const action=b.dataset.cleanAction;
 if(action==='sessions')return $('#btnSessions').click();
 if(action==='usage')return $('#btnUsage').click();
 if(action==='voice'){await $('#btnVoice').onclick();return openControls('root');}
 if(action==='language')return $('#btnLang').click();
 if(action==='install')return $('#btnHomeScreen').click();
 if(action==='home')return showAssistantHome();
});
if(tg?.BackButton?.onClick)tg.BackButton.onClick(()=>{if(!$('#sheet').classList.contains('hidden'))closeSheet();else showAssistantHome();});
setNav();

$('#homeSsh').onclick=()=>switchWorkspace(engine,'ssh');

// Local album drafts reuse the existing authenticated upload and image path transport.
const albums={claude:[],codex:[]};let photoSequence=0,forceChatBottom=false;
function drawAlbum(){
 if(S.tab==='ssh')return;
 const c=$('#chat'),wasNearBottom=c.scrollHeight-c.clientHeight-c.scrollTop<120;
 const items=albums[engine],ready=items.find(x=>x.status==='ready');
 S.image=ready?.id||null;attachments[engine]=S.image;
 $('#preview').classList.toggle('hidden',!items.length);
 const signature=items.map(x=>x.key+':'+x.status).join('|');if($('#albumPreview').dataset.signature!==signature){$('#albumPreview').dataset.signature=signature;$('#albumPreview').innerHTML=items.map(x=>'<div class="album-thumb '+x.status+'"><img src="'+esc(x.url)+'" alt="'+esc(x.name)+'"><button type="button" data-remove-photo="'+x.key+'" aria-label="'+tr('remove')+'">×</button><small>'+(x.status==='uploading'?tr('wait'):x.status==='failed'?(uiLanguage==='fa'?'ناموفق':'Failed'):'')+'</small></div>').join('');}
 $('#previewX').ariaLabel=uiLanguage==='fa'?'حذف همه عکس‌ها':'Remove all photos';autosize();
 $('#btnSend').disabled=items.some(x=>x.status==='uploading');if(wasNearBottom&&view==='chat')jumpChatToLatest(false);
}
$('#albumPreview').addEventListener('click',e=>{const b=e.target.closest('[data-remove-photo]');if(!b)return;albums[engine]=albums[engine].filter(x=>x.key!==+b.dataset.removePhoto);drawAlbum();});
const priorAlbumBubble=bubble;
bubble=function(m,i){const el=priorAlbumBubble(m,i);if(m.photos?.length){const box=document.createElement('div');box.className='sent-album';for(const photo of m.photos){const img=document.createElement('img');img.src=photo.url;img.alt=photo.name;box.appendChild(img);}el.prepend(box);}return el;};
function updateLatestButton(){const c=$('#chat');$('#jumpLatest').classList.toggle('hidden',view==='home'||S.tab==='ssh'||c.scrollHeight-c.clientHeight-c.scrollTop<120);$('#jumpLatest').ariaLabel=uiLanguage==='fa'?'آخرین پیام':'Latest messages';}
function jumpChatToLatest(smooth=false){const c=$('#chat');c.scrollTo({top:c.scrollHeight,behavior:smooth&&!matchMedia('(prefers-reduced-motion: reduce)').matches?'smooth':'auto'});updateLatestButton();}
$('#jumpLatest').onclick=()=>jumpChatToLatest(true);$('#chat').addEventListener('scroll',updateLatestButton,{passive:true});
new ResizeObserver(entries=>{document.documentElement.style.setProperty('--composer-height',entries[0].target.offsetHeight+'px');updateLatestButton();}).observe($('.composer'));
const priorAlbumRender=render;let renderedThread=null;
render=function(){
 const c=$('#chat'),key=S.tab+':'+(S.data[S.tab]?.current||''),position=c.scrollTop,readingOlder=view!=='home'&&S.tab!=='ssh'&&renderedThread===key&&c.scrollHeight-c.clientHeight-position>120;
 priorAlbumRender();
 if(view!=='home'&&S.tab!=='ssh'){if(readingOlder&&!forceChatBottom)c.scrollTop=position;else jumpChatToLatest(false);renderedThread=key;drawAlbum();}
 forceChatBottom=false;updateLatestButton();
};
const priorAlbumSwitch=switchWorkspace;
switchWorkspace=async function(...args){await priorAlbumSwitch(...args);if(S.tab!=='ssh')drawAlbum();updateLatestButton();};
const priorHistoryRefresh=refresh;
refresh=async function(...args){const d=await priorHistoryRefresh(...args);if(d.history)for(const m of S.msgs[args[0]])if(m.role==='user')m.text=m.text.replace(/\n*\(CLODEX_ATTACHMENTS:[^)]*\)/g,'').trim()||(uiLanguage==='fa'?'عکس‌ها':'Photos');return d;};

window.addEventListener('pageshow',e=>{if(e.persisted&&view!=='home'&&S.tab!=='ssh'){scrolls[S.tab]=null;requestAnimationFrame(()=>jumpChatToLatest(false));}});

new ResizeObserver(()=>updateLatestButton()).observe($('#chat'));

// Each section owns its settings; no bottom tab navigation.
$('#workspaceSettings').onclick=()=>S.tab==='ssh'?openSshSettings():openControls('root',engine);
async function openSshSettings(){
 const token=++controlsEpoch;view='ssh-settings';setNav();sheet('<h3>SSH · '+tr('settings')+'</h3><p>'+tr('wait')+'</p>');
 if(!SSH.servers.length)await sshShow();
 if(token!==controlsEpoch||S.tab!=='ssh'||$('#sheet').classList.contains('hidden'))return;
 let h='<h3>SSH · '+tr('settings')+'</h3><div class="ssh-settings-list">';
 for(const server of SSH.servers)h+='<div class="ssh-settings-row"><button data-ssh-connect="'+esc(server.id)+'">'+esc(server.name)+'</button>'+(!server.local?'<button class="ssh-edit" data-ssh-edit="'+esc(server.id)+'">'+(uiLanguage==='fa'?'ویرایش':'Edit')+'</button>':'')+'</div>';
 h+='</div><div class="workspace-options"><button data-ssh-add>'+(uiLanguage==='fa'?'افزودن سرور':'Add server')+'</button><button data-ssh-language>'+(uiLanguage==='fa'?'زبان برنامه · فارسی':'App language · English')+'</button><button data-clean-action="home">'+(uiLanguage==='fa'?'صفحهٔ شروع':'Home')+'</button><button data-clean-action="install">'+tr('install')+'</button></div>';sheet(h);
}
$('#sheetContent').addEventListener('click',e=>{
 const connect=e.target.closest('[data-ssh-connect]'),edit=e.target.closest('[data-ssh-edit]');
 if(connect){sshConnect(connect.dataset.sshConnect);closeSheet();}
 else if(edit)serverSheet(edit.dataset.sshEdit);
 else if(e.target.closest('[data-ssh-add]'))serverSheet(null);
 else if(e.target.closest('[data-ssh-language]')){$('#btnLang').click();openSshSettings();}
});
const priorSectionRender=render;
render=function(){priorSectionRender();$('#workspaceSettings').ariaLabel=tr('settings');$('#thinkingLogo').src='s/'+(engine==='claude'?'claude.svg':'openai.svg?v=white22');$('#busyText').dataset.thinking=engine==='codex'&&S.data.codex?.job?.progress?tr('thinking'):'';};

// Claude chat follows the supplied reference; other workspaces keep their layout.
const beforeClaudeBubble=bubble;
function voiceTime(seconds){if(!Number.isFinite(seconds))return '';return Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');}
bubble=function(m,i){
 if(S.tab!=='claude')return beforeClaudeBubble(m,i);
 const el=beforeClaudeBubble(m,i);
 if(m.role==='user'&&m.voiceUrl){
  el.classList.add('voice-note');
  const attachedPhotos=el.querySelector('.sent-album');
  el.innerHTML='<div class="voice"><button class="play" data-i="'+i+'" aria-label="'+tr('play')+'"><svg class="ic-play" viewBox="0 0 24 24"><path d="M7 5L17 12L7 19Z"/></svg><svg class="ic-pause" viewBox="0 0 24 24"><path d="M7 6h4v12H7zm6 0h4v12h-4z"/></svg></button><div class="wave"></div><span class="audio-status"></span><button class="stop-audio" data-stop-audio="'+i+'" aria-label="'+tr('stopAudio')+'"><svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1"/></svg></button></div><button class="show" data-i="'+i+'">'+tr('showText')+'</button><div class="hid hidden">'+md(m.text)+'</div>';
  if(attachedPhotos)el.prepend(attachedPhotos);
 }
 const voice=el.querySelector('.voice');
 if(voice){
  const wave=voice.querySelector('.wave');const levels=[3,5,10,16,9,23,29,17,12,25,18,9,5,12,20,13,7,14,10,5,3,6,3,2];
  wave.innerHTML=levels.map((height,j)=>'<i style="--wave-height:'+height+'px;--wave-delay:'+(-j*.08)+'s"></i>').join('');
  const duration=document.createElement('span');duration.className='audio-duration';duration.textContent=voiceTime(m.duration);voice.insertBefore(duration,voice.querySelector('.stop-audio'));
 }
 return el;
};
const beforeClaudeVoicePaint=paintVoice;
paintVoice=function(){beforeClaudeVoicePaint();if(S.tab==='claude')document.querySelectorAll('.voice').forEach(box=>{const m=S.msgs.claude[+box.querySelector('.play').dataset.i];const duration=box.querySelector('.audio-duration');if(duration)duration.textContent=voiceTime(m?.duration);});};

$('#homePanel').onclick=async()=>{try{if(!SSH.servers.length)SSH.servers=(await getJSON('/ssh/servers')).servers;}catch(e){}const s=SSH.servers.find(x=>x.link);if(!s)return toast(uiLanguage==='fa'?'لینک پنل ثبت نشده؛ در SSH روی سرور پنل لینک بگذار':'No panel link saved');location.assign(s.link);};

/* نمایش بزرگ عکس مثل تلگرام: لمس عکس → تمام‌صفحه با دکمه‌ی دانلود */
(()=>{const v=document.createElement('div');v.id='imgViewer';v.className='img-viewer hidden';v.innerHTML='<div class="iv-stage"><img alt=""></div><div class="iv-bar"><button type="button" class="iv-close" aria-label="بستن">×</button><button type="button" class="iv-dl">دانلود</button></div>';document.body.appendChild(v);const img=v.querySelector('img');let fid=null,name='';
const close=()=>{v.classList.add('hidden');img.src='';};
v.querySelector('.iv-close').onclick=close;v.querySelector('.iv-stage').onclick=e=>{if(e.target!==img)close();};
v.querySelector('.iv-dl').onclick=async()=>{if(!fid)return;try{const {url}=await getJSON('/file/'+fid+'/link');if(tg&&tg.downloadFile&&tg.isVersionAtLeast&&tg.isVersionAtLeast('8.0')){tg.downloadFile({url,file_name:name});}else if(tg&&tg.openLink){tg.openLink(url);}else{const a=document.createElement('a');a.href=url;a.download=name;a.click();}}catch(e){toast(uiLanguage==='fa'?'دانلود نشد':'Download failed');}};
$('#chat').addEventListener('click',e=>{const pic=e.target.closest('img.pic');if(!pic)return;const btn=pic.previousElementSibling;fid=btn&&btn.dataset.fid;name=(btn&&btn.dataset.name)||'image.png';img.src=pic.src;v.classList.remove('hidden');});
document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});})();

/* صفحه‌ی SSH خلوت: سرورها، افزودن سرور و کلیدهای کمکی همه داخل دکمه‌ی + */
(()=>{const old=$('#termKeys'),plus=old.cloneNode(true);old.replaceWith(plus);plus.textContent='+';plus.setAttribute('aria-label','سرورها و کلیدها');
const toggleKeys=()=>{const keys=$('#keys');keys.hidden=!keys.hidden;requestAnimationFrame(()=>{try{sshFit();}catch(e){}});};
plus.addEventListener('pointerdown',e=>e.preventDefault());
plus.addEventListener('click',async()=>{if(!SSH.servers.length){try{SSH.servers=(await getJSON('/ssh/servers')).servers;}catch(e){}}
const rows=SSH.servers.map(s=>'<div class="control-row"><button data-ssh-go="'+esc(s.id)+'"'+(s.id===SSH.cur?' class="confirm"':'')+'>›_ '+esc(s.name)+'</button>'+(s.id==='local'?'':'<button data-ssh-edit="'+esc(s.id)+'" style="flex:0 0 auto">ویرایش</button>')+'</div>').join('');
sheet('<h3>سرورها</h3><div class="control-grid">'+rows+'<div class="control-row"><button data-ssh-add>+ افزودن سرور</button></div><div class="control-row"><button data-ssh-keys>'+($('#keys').hidden?'نمایش کلیدهای کمکی':'بستن کلیدهای کمکی')+'</button></div></div>');});
$('#sheetContent').addEventListener('click',e=>{const go=e.target.closest('[data-ssh-go]'),ed=e.target.closest('[data-ssh-edit]');
if(go){closeSheet();sshConnect(go.dataset.sshGo);}else if(ed){serverSheet(ed.dataset.sshEdit);}else if(e.target.closest('[data-ssh-add]')){serverSheet(null);}else if(e.target.closest('[data-ssh-keys]')){closeSheet();toggleKeys();}});
const msg=$('#termMsg span:last-child');if(msg)msg.textContent='برای اتصال، دکمه‌ی + را بزن و سرور را انتخاب کن';})();

// Hide transport-generated preference lines from historical user bubbles.
function stripGeneratedPrefs(text){return String(text||'').replace(/(?:\n+(?:Reply (?:concisely|in (?:English|the language used in the current user message))[^\n]*|به فارسی و کوتاه[^\n]*|Use a [^\n]*tone[^\n]*))+\s*$/,'').trim();}
const bubbleBeforePrefsCleanup=bubble;
bubble=function(m,i){if(m.role==='user'){const text=stripGeneratedPrefs(m.text);if(text!==String(m.text||''))return bubbleBeforePrefsCleanup({...m,text},i);}return bubbleBeforePrefsCleanup(m,i);};
