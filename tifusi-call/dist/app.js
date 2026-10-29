'use strict';
const $=id=>document.getElementById(id);
const API=location.hostname.endsWith('.chatgpt.site')?'https://app.bomalo.ir/call':location.origin+'/call';
const C={room:null,token:null,role:null,invite:null,expires:0,stream:null,remote:null,pc:null,ws:null,senders:{},candidates:[],generation:0,active:false,epoch:0,mic:true,camera:false,facing:'user',name:'',peerName:'دوستت',peerCamera:false,peerMic:true,retries:0,connectedAt:0,offerBusy:false,iceFailures:0,qualityMode:'auto',lowBandwidth:false,goodSamples:0,net:{},statsPrevious:new Map(),tuning:Promise.resolve(),wsTimer:null,iceTimer:null,tick:null,statsTimer:null};
const inputLink=new URLSearchParams(location.hash.slice(1));
let joining=inputLink.has('r')&&inputLink.has('k'),busy=false,toastTimer;
const faNumber=n=>String(n).replace(/\d/g,x=>'۰۱۲۳۴۵۶۷۸۹'[x]);
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
function view(id){for(const k of ['home','call','ended'])$(k).hidden=k!==id;document.querySelector('meta[name=theme-color]').content=id==='call'?'#243d32':'#f6f4ef';}
function status(text,tone=''){const box=$('connectionStatus');box.className='connection-status '+tone;box.querySelector('span').textContent=text;}
function notice(text){$('callNotice').textContent=text;}
function mediaError(e){return ({NotAllowedError:'اجازهٔ میکروفن یا دوربین داده نشده. از تنظیمات مرورگر اجازه بده و دوباره بزن.',NotFoundError:'میکروفن یا دوربین پیدا نشد. برای تماس صوتی، گزینهٔ «فقط صوتی» رو انتخاب کن.',NotReadableError:'دوربین یا میکروفن درگیر برنامهٔ دیگه‌ایه؛ اون برنامه رو ببند و دوباره امتحان کن.',OverconstrainedError:'این دوربین با تنظیمات تماس سازگار نیست؛ تماس صوتی رو امتحان کن.',SecurityError:'تماس رو در مرورگر اصلی و با اتصال امن باز کن.'})[e.name]||e.message||'ارتباط برقرار نشد؛ دوباره امتحان کن.';}
async function request(path,data){const r=await fetch(API+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),cache:'no-store'});if(!r.ok){const text=await r.text();const e=new Error(text.startsWith('<')?'سرویس موقتاً در دسترس نیست.':text.slice(0,200));e.status=r.status;throw e;}return r.json();}
function send(data){if(C.ws?.readyState===WebSocket.OPEN)C.ws.send(JSON.stringify({...data,generation:C.generation}));}
function auth(){return {room:C.room,token:C.token};}
function inviteURL(){const base=location.origin+location.pathname;return base+'#'+new URLSearchParams({r:C.room,k:C.invite}).toString();}
function localView(){const video=C.stream?.getVideoTracks()[0];C.camera=!!video&&video.enabled&&video.readyState==='live';$('localVideo').srcObject=C.stream;$('localAvatar').hidden=C.camera;$('localVideo').style.opacity=C.camera?'1':'0';$('localVideo').closest('.local-tile').classList.toggle('rear',C.facing==='environment');$('localVideo').play().catch(()=>{});$('cameraButton').setAttribute('aria-pressed',String(!C.camera));$('cameraButton').setAttribute('aria-label',C.camera?'خاموش‌کردن دوربین':'روشن‌کردن دوربین');$('micButton').setAttribute('aria-pressed',String(!C.mic));$('micButton').setAttribute('aria-label',C.mic?'خاموش‌کردن میکروفن':'روشن‌کردن میکروفن');$('flipButton').disabled=!C.camera;}
function remoteView(){const show=!!C.pc&&C.pc.connectionState==='connected'&&C.peerCamera;$('remotePlaceholder').hidden=show;$('remoteVideo').style.opacity=show?'1':'0';$('remoteName').textContent=C.pc?.connectionState==='connected'?C.peerName:'جای دوستت خالیه';$('remoteAvatar').textContent=C.pc?.connectionState==='connected'?C.peerName.slice(0,1):'✳';if(C.pc?.connectionState==='connected')$('remoteHint').textContent=C.peerMic?'در حال گفت‌وگو؛ دوربین خاموشه.':'میکروفن دوستت خاموشه.';}
function shareMedia(){send({type:'media',mic:C.mic,camera:C.camera});}

const cameraConstraints=()=>({width:{ideal:480,max:640},height:{ideal:360,max:480},frameRate:{ideal:15,max:15},facingMode:C.facing});
function tuneReceivers(pc){for(const rx of pc.getReceivers())try{if('jitterBufferTarget' in rx)rx.jitterBufferTarget=40;else if('playoutDelayHint' in rx)rx.playoutDelayHint=.04;}catch{}}
function tuneSenders(){
 const pc=C.pc;if(!pc)return Promise.resolve();
 C.tuning=C.tuning.catch(()=>{}).then(async()=>{
  if(C.pc!==pc)return;
  for(const [kind,sender] of Object.entries(C.senders)){
   if(!sender.track)continue;
   const params=sender.getParameters();if(!params.encodings?.length)continue;
   for(const enc of params.encodings){enc.maxBitrate=kind==='audio'?24000:C.lowBandwidth?70000:180000;enc.priority=kind==='audio'?'high':'low';if(kind==='video'){enc.maxFramerate=C.lowBandwidth?10:15;enc.scaleResolutionDownBy=C.lowBandwidth?1.5:1;}}
   if(kind==='video')params.degradationPreference='maintain-framerate';
   try{await sender.setParameters(params);}catch{try{const fallback=sender.getParameters();for(const enc of fallback.encodings||[])enc.maxBitrate=kind==='audio'?24000:C.lowBandwidth?70000:180000;await sender.setParameters(fallback);}catch{}}
  }
 });return C.tuning;
}
function showNetwork(){
 const n=C.net;const path=n.transport==='tcp'?'رلهٔ TCP':n.transport==='udp'?'رلهٔ UDP':n.transport==='direct'?'مستقیم':n.transport==='relay'?'رله':'در حال اندازه‌گیری';
 $('networkInfo').textContent='مسیر: '+path+(n.rttMs!=null?' · رفت‌وبرگشت: '+faNumber(Math.round(n.rttMs))+' میلی‌ثانیه':'')+(n.audioBufferMs!=null?' · بافر صدا: '+faNumber(Math.round(n.audioBufferMs))+' میلی‌ثانیه':'');
 $('qualityButton').textContent=C.qualityMode==='low'?'ارسال کم‌مصرف فعال است؛ بازگشت به خودکار':C.lowBandwidth?'کیفیت خودکار: تصویر سبک‌تر':'کیفیت خودکار؛ فعال‌کردن ارسال کم‌مصرف';$('qualityButton').setAttribute('aria-pressed',String(C.qualityMode==='low'));
}
async function networkStats(){
 const pc=C.pc;if(pc?.connectionState!=='connected')return;
 try{
  const stats=await pc.getStats();if(C.pc!==pc)return;const n={};
  stats.forEach(x=>{
   if(x.type==='candidate-pair'&&x.state==='succeeded'&&x.nominated){const local=stats.get(x.localCandidateId),remote=stats.get(x.remoteCandidateId);const relay=[local,remote].find(c=>c?.candidateType==='relay');n.transport=local?.candidateType==='relay'?(local.relayProtocol||'relay'):remote?.candidateType==='relay'?'relay':'direct';if(x.currentRoundTripTime!=null)n.rttMs=x.currentRoundTripTime*1000;if(x.availableOutgoingBitrate!=null)n.available=x.availableOutgoingBitrate;}
   if(x.type==='inbound-rtp'){
    const before=C.statsPrevious.get(x.id),count=x.jitterBufferEmittedCount-(before?.jitterBufferEmittedCount||0),delay=x.jitterBufferDelay-(before?.jitterBufferDelay||0);
    if(count>0)n[x.kind+'BufferMs']=delay/count*1000;
    const received=x.packetsReceived-(before?.packetsReceived||0),lost=Math.max(0,(x.packetsLost||0)-(before?.packetsLost||0));if(received+lost>0)n.loss=Math.max(n.loss||0,lost/(received+lost));
    C.statsPrevious.set(x.id,x);
   }
  });C.net=n;
  const weak=n.rttMs>450||n.audioBufferMs>250||n.videoBufferMs>400||n.loss>.04||(n.available!=null&&n.available<220000);
  if(weak){C.goodSamples=0;if(!C.lowBandwidth){C.lowBandwidth=true;await tuneSenders();}notice('برای کمتر شدن مکث، حالت کم‌مصرف فعال شد.');}
  else if(C.qualityMode==='auto'&&C.lowBandwidth&&++C.goodSamples>=4){C.lowBandwidth=false;await tuneSenders();notice('');}
  showNetwork();
 }catch{}
}

async function acquire(mode,epoch){
 if(!isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.RTCPeerConnection)throw new Error('این مرورگر تماس امن رو پشتیبانی نمی‌کنه؛ لینک رو در Safari یا Chrome باز کن.');
 if(navigator.audioSession)try{navigator.audioSession.type='play-and-record';}catch{}
 const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1},video:mode==='video'?cameraConstraints():false});
 if(C.epoch!==epoch){stream.getTracks().forEach(t=>t.stop());throw new DOMException('Cancelled','AbortError');}
 C.stream=stream;C.mic=true;C.facing='user';localView();
}
function closePC(){C.statsPrevious.clear();clearTimeout(C.iceTimer);C.iceTimer=null;if(C.pc){C.pc.ontrack=null;C.pc.onconnectionstatechange=null;C.pc.onicecandidate=null;C.pc.close();C.pc=null;}C.senders={};C.candidates=[];C.offerBusy=false;C.remote=null;$('remoteVideo').srcObject=null;remoteView();}
async function makePC(){
 closePC();C.remote=new MediaStream();$('remoteVideo').srcObject=C.remote;
 const pc=new RTCPeerConnection({iceServers:C.iceServers,iceTransportPolicy:location.search.includes('relay=1')?'relay':'all',bundlePolicy:'max-bundle'});C.pc=pc;
 if(C.role==='host')for(const kind of ['audio','video']){const tx=pc.addTransceiver(kind,{direction:'sendrecv'});C.senders[kind]=tx.sender;const track=C.stream?.getTracks().find(t=>t.kind===kind);if(track)await tx.sender.replaceTrack(track);}
 await tuneSenders();tuneReceivers(pc);
 pc.onicecandidate=e=>{if(C.pc===pc&&e.candidate)send({type:'candidate',candidate:e.candidate.toJSON()});};
 pc.ontrack=e=>{if(C.pc!==pc)return;tuneReceivers(pc);C.remote.addTrack(e.track);e.track.onunmute=()=>{remoteView();$('remoteVideo').play().catch(()=>$('playButton').hidden=false);};$('remoteVideo').play().catch(()=>$('playButton').hidden=false);};
 pc.onconnectionstatechange=()=>{
  if(C.pc!==pc||!C.active)return;
  if(pc.connectionState==='connected'){tuneSenders();tuneReceivers(pc);networkStats();clearTimeout(C.iceTimer);C.iceFailures=0;status('وصل شدیم','connected');notice('');$('roomTitle').textContent='در گفت‌وگو با '+C.peerName;$('remoteName').textContent=C.peerName;$('retryButton').hidden=true;if(!C.connectedAt)C.connectedAt=Date.now();shareMedia();remoteView();}
  else if(pc.connectionState==='failed'||pc.connectionState==='disconnected'){status('داریم اتصال رو برمی‌گردونیم…','warn');clearTimeout(C.iceTimer);C.iceTimer=setTimeout(()=>restartICE(),pc.connectionState==='failed'?1000:6000);}
 };
}
async function offer(restart=false){const pc=C.pc;if(!pc||C.role!=='host'||C.offerBusy||pc.signalingState!=='stable')return;C.offerBusy=true;try{const sdp=await pc.createOffer({iceRestart:restart});if(C.pc!==pc)return;await pc.setLocalDescription(sdp);send({type:'offer',description:pc.localDescription.toJSON()});}finally{C.offerBusy=false;}}
async function restartICE(){if(!C.active||!C.pc)return;if(++C.iceFailures>3){notice('اتصال برنگشت؛ اینترنت هر دو نفر رو بررسی کنید و دوباره تلاش کنید.');$('retryButton').hidden=false;return;}if(C.role==='host')await offer(true).catch(()=>{});else send({type:'restart'});C.iceTimer=setTimeout(()=>{if(C.pc?.connectionState!=='connected')restartICE();},10000);}
async function signal(data){
 if(!C.active)return;
 if(data.type==='error'){finish(data.message||'ورود به این اتاق ممکن نیست.');return;}
 if(data.type==='ended'){finish(data.reason==='expired'?'اعتبار یک‌ساعتهٔ اتاق تموم شد. یک تماس تازه بساز.':data.reason==='restart'?'سرویس دوباره راه افتاد؛ یک تماس تازه بساز.':'تماس تموم شد و میکروفن و دوربینت خاموش شدن.');return;}
 if(data.type==='joined'){C.retries=0;status('منتظر نفر دوم');return;}
 if(data.type==='peer'){C.peerName=data.name||'دوستت';return;}
 if(data.type==='peer-left'){closePC();C.peerCamera=false;status('دوستت از اتصال خارج شد','warn');$('roomTitle').textContent='منتظر برگشت دوستت';$('remoteHint').textContent='اگر اینترنتش قطع شده باشه، برای برگشت تلاش می‌کنیم.';notice('اتاق هنوز بازه؛ دوستت می‌تونه با همون لینک برگرده.');return;}
 if(data.type==='ready'){C.generation=data.generation;C.peerCamera=false;await makePC();status('داریم وصل می‌شیم…');shareMedia();await offer();return;}
 if(data.type==='media'){C.peerCamera=!!data.camera;C.peerMic=!!data.mic;C.peerName=data.name||C.peerName;remoteView();return;}
 if(data.type==='restart'){await offer(true);return;}
 if(data.generation!==C.generation)return;
 const pc=C.pc;if(!pc)return;
 if(data.type==='candidate'){if(pc.remoteDescription)await pc.addIceCandidate(data.candidate);else C.candidates.push(data.candidate);}
 if(data.type==='offer'||data.type==='answer'){
  await pc.setRemoteDescription(data.description);
  for(const c of C.candidates.splice(0))await pc.addIceCandidate(c);
  if(data.type==='offer'){for(const tx of pc.getTransceivers()){const kind=tx.receiver.track.kind;tx.direction='sendrecv';C.senders[kind]=tx.sender;await tx.sender.replaceTrack(C.stream?.getTracks().find(t=>t.kind===kind)||null);}await tuneSenders();tuneReceivers(pc);await pc.setLocalDescription(await pc.createAnswer());send({type:'answer',description:pc.localDescription.toJSON()});}
 }
}
function connect(){
 if(!C.active)return;clearTimeout(C.wsTimer);const epoch=C.epoch;
 const ws=new WebSocket(API.replace(/^http/,'ws')+'/ws');C.ws=ws;let chain=Promise.resolve();
 ws.onopen=()=>{if(!C.active||epoch!==C.epoch){ws.close();return;}ws.send(JSON.stringify({...auth(),name:C.name}));};
 ws.onmessage=e=>{chain=chain.then(async()=>{if(C.ws!==ws||epoch!==C.epoch)return;await signal(JSON.parse(e.data));}).catch(()=>{notice('هماهنگی تماس قطع شد؛ دوباره تلاش می‌کنیم.');if(C.active&&C.ws===ws)ws.close();});};
 ws.onclose=()=>{if(!C.active||C.ws!==ws||epoch!==C.epoch)return;closePC();status('ارتباط قطع شد؛ تلاش دوباره…','warn');const delay=Math.min(1000*2**C.retries++,12000);C.wsTimer=setTimeout(()=>{if(Date.now()/1000>=C.expires)finish('اعتبار لینک تموم شده؛ یک تماس تازه بساز.');else connect();},delay);};
 ws.onerror=()=>{};
}
async function start(mode){
 const epoch=++C.epoch;
 await acquire(mode,epoch);
 let accepted=false;
 try{
  if(joining){C.room=inputLink.get('r');C.token=inputLink.get('k');}
  else{const room=await request('/api/rooms',{mode});C.room=room.room;C.token=room.token;C.invite=room.invite;C.expires=room.expires;}
  const info=await request('/api/info',auth());
  if(C.epoch!==epoch)throw new DOMException('Cancelled','AbortError');
  C.role=info.role;C.expires=info.expires;C.iceServers=info.iceServers;C.active=true;accepted=true;C.name=$('name').value.trim()||'دوستت';C.connectedAt=0;C.iceFailures=0;C.retries=0;C.qualityMode='auto';C.lowBandwidth=false;C.goodSamples=0;C.net={};C.statsPrevious.clear();showNetwork();
  $('inviteCard').hidden=C.role!=='host';if(C.invite)$('inviteDisplay').textContent=location.host+'/… • دعوت خصوصی';$('roomTitle').textContent=C.role==='host'?'منتظر دوستت هستیم':'داریم به دوستت وصل می‌شیم';$('retryButton').hidden=true;$('remoteHint').textContent=C.role==='host'?'لینک رو براش بفرست تا بهت ملحق بشه.':'چند لحظه صبر کن تا هر دو نفر آماده بشن.';view('call');connect();
  C.tick=setInterval(()=>{const elapsed=C.connectedAt?Math.floor((Date.now()-C.connectedAt)/1000):0;$('callClock').textContent=faNumber(String(Math.floor(elapsed/60)).padStart(2,'0')+':'+String(elapsed%60).padStart(2,'0'));if(Date.now()/1000>=C.expires)finish('اعتبار اتاق تموم شد. برای ادامه یک تماس تازه بساز.');},1000);
  C.statsTimer=setInterval(networkStats,2000);
 }finally{if(!accepted){C.stream?.getTracks().forEach(t=>t.stop());C.stream=null;}}
}
function finish(message){
 C.active=false;C.epoch++;clearTimeout(C.wsTimer);clearTimeout(C.iceTimer);clearInterval(C.tick);clearInterval(C.statsTimer);C.ws?.close();C.ws=null;closePC();C.stream?.getTracks().forEach(t=>t.stop());C.stream=null;$('localVideo').srcObject=null;$('playButton').hidden=true;C.invite=null;C.token=null;C.room=null;$('endText').textContent=message;history.replaceState(null,'',location.pathname);joining=false;view('ended');
}
$('startForm').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;busy=true;$('startButton').disabled=true;$('formError').hidden=true;$('startLabel').textContent='در حال آماده‌شدن…';try{await start(document.querySelector('[name=mode]:checked').value);}catch(err){if(err.name!=='AbortError'){$('formError').textContent=mediaError(err);$('formError').hidden=false;}}finally{busy=false;$('startButton').disabled=false;$('startLabel').textContent=joining?'پیوستن به تماس':'ساخت اتاق تماس';}});
$('micButton').onclick=()=>{C.mic=!C.mic;C.stream?.getAudioTracks().forEach(t=>t.enabled=C.mic);localView();shareMedia();};
$('cameraButton').onclick=async()=>{
 const epoch=C.epoch;const b=$('cameraButton');b.disabled=true;
 try{const old=C.stream?.getVideoTracks()[0];if(old&&C.camera){if(C.senders.video)await C.senders.video.replaceTrack(null);old.stop();C.stream.removeTrack(old);}else{const stream=await navigator.mediaDevices.getUserMedia({video:cameraConstraints(),audio:false});if(!C.active||C.epoch!==epoch){stream.getTracks().forEach(t=>t.stop());return;}const track=stream.getVideoTracks()[0];if(C.senders.video)await C.senders.video.replaceTrack(track);if(old){old.stop();C.stream.removeTrack(old);}C.stream.addTrack(track);}await tuneSenders();localView();shareMedia();}catch(e){toast(mediaError(e));}finally{b.disabled=false;}
};
$('flipButton').onclick=async()=>{
 if(!C.camera)return;const epoch=C.epoch;const b=$('flipButton');b.disabled=true;const old=C.stream.getVideoTracks()[0];const facing=C.facing==='user'?'environment':'user';
 try{old.stop();const stream=await navigator.mediaDevices.getUserMedia({video:{...cameraConstraints(),facingMode:{ideal:facing}},audio:false});if(!C.active||C.epoch!==epoch){stream.getTracks().forEach(t=>t.stop());return;}const track=stream.getVideoTracks()[0];if(C.senders.video)await C.senders.video.replaceTrack(track);C.stream.removeTrack(old);C.stream.addTrack(track);C.facing=facing;await tuneSenders();localView();shareMedia();}catch(e){localView();shareMedia();toast(mediaError(e));}finally{b.disabled=!C.camera;}
};
$('endButton').onclick=async()=>{const data=auth();send({type:'end'});finish('تماس تموم شد و میکروفن و دوربینت خاموش شدن.');request('/api/end',data).catch(()=>{});};
$('qualityButton').onclick=async()=>{C.qualityMode=C.qualityMode==='auto'?'low':'auto';C.lowBandwidth=C.qualityMode==='low';C.goodSamples=0;await tuneSenders();showNetwork();toast(C.lowBandwidth?'ارسال تصویر سبک‌تر شد؛ وضوحش کمتر می‌شه.':'کیفیت خودکار فعال شد.');};
$('retryButton').onclick=()=>{C.iceFailures=0;$('retryButton').hidden=true;restartICE();};
$('copyButton').onclick=async()=>{if(!C.invite)return;try{await navigator.clipboard.writeText(inviteURL());toast('لینک دعوت کپی شد؛ برای دوستت بفرست.');}catch{const text=inviteURL();const input=document.createElement('textarea');input.value=text;input.style.position='fixed';input.style.top='-9999px';document.body.append(input);input.select();const ok=document.execCommand('copy');input.remove();if(ok)toast('لینک دعوت کپی شد.');else{prompt('این لینک رو کپی کن:',text);}}};
$('shareButton').onclick=async()=>{if(!C.invite)return;if(navigator.share){try{await navigator.share({title:'بیا هم‌صدا بشیم',text:'برای تماس دونفره وارد این لینک شو:',url:inviteURL()});}catch(e){if(e.name!=='AbortError')$('copyButton').click();}}else $('copyButton').click();};
$('playButton').onclick=()=>$('remoteVideo').play().then(()=>$('playButton').hidden=true).catch(()=>toast('صدای دستگاه و مجوز مرورگر رو بررسی کن.'));
$('againButton').onclick=()=>{C.peerName='دوستت';C.peerCamera=false;$('formError').hidden=true;view('home');$('welcomeTitle').textContent='یه گفت‌وگو شروع کن';$('welcomeText').textContent='اتاقت رو بساز و لینک رو برای دوستت بفرست.';$('startLabel').textContent='ساخت اتاق تماس';$('modeField').hidden=false;};
function modeNote(){const video=document.querySelector('[name=mode]:checked').value==='video';$('permissionNote').textContent=video?'قبل از ورود، اجازهٔ میکروفن و دوربین رو می‌گیریم.':'فقط اجازهٔ میکروفن لازمه؛ دوربین خاموش می‌مونه.';}
for(const input of document.querySelectorAll('[name=mode]'))input.onchange=modeNote;
$('helpButton').onclick=()=>$('helpDialog').showModal();$('closeHelp').onclick=()=>$('helpDialog').close();$('helpDialog').onclick=e=>{if(e.target===$('helpDialog'))$('helpDialog').close();};
window.addEventListener('offline',()=>{if(C.active){status('اینترنت قطع شده','warn');notice('وقتی اینترنت برگرده، دوباره برای اتصال تلاش می‌کنیم.');}});
window.addEventListener('online',()=>{if(!C.active)return;if(C.ws?.readyState!==WebSocket.OPEN){C.ws?.close();connect();}else restartICE();});
window.addEventListener('pagehide',()=>{C.epoch++;C.active=false;C.ws?.close();C.pc?.close();C.stream?.getTracks().forEach(t=>t.stop());clearInterval(C.tick);clearInterval(C.statsTimer);clearTimeout(C.wsTimer);clearTimeout(C.iceTimer);});
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
if(joining){$('welcomeTitle').textContent='دوستت دعوتت کرده';$('welcomeText').textContent='اسمت رو بنویس، نوع تماس رو انتخاب کن و بپیوند.';$('cardKicker').textContent='این بار سلام از دوستته';$('startLabel').textContent='پیوستن به تماس';}
modeNote();
