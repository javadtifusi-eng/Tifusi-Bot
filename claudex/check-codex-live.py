from pathlib import Path
from urllib.parse import urlparse,parse_qs
import mimetypes,json
from playwright.sync_api import sync_playwright
import os,tempfile
root=Path(os.environ.get('CLODEX_STATIC',str(Path(__file__).parent/'static')));out=Path(tempfile.mkdtemp(prefix='codex-live-preview-'))
state=lambda engine:dict(current='session-'+engine,model='opus' if engine=='claude' else 'gpt-6',models=[{'id':'opus','label':'Opus'},{'id':'gpt-6','label':'GPT-6'}],sessions=[{'id':'session-'+engine,'title':'گفتگوی آزمایشی'}],voice=False,job=None,history=[{'role':'user','text':'سلام، ظاهر جدید آماده است؟'},{'role':'assistant','text':'بله، طرح تازه آماده است.\n\n```sh\nprintf hello\n```'}])
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 for width,inset in [(390,66)]:
  context=browser.new_context(viewport={'width':width,'height':844},permissions=['clipboard-read','clipboard-write'])
  page=context.new_page();errors=[];requests=[];events=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  livejob=None;sendcount=0;failstt=False
  def handle(route):
   global livejob,sendcount,failstt
   path=urlparse(route.request.url).path;engine='codex' if '/codex/' in path else 'claude'
   if path=='/claudex/s/telegram-web-app.js':
    sdk="window.tgEvents={};window.Telegram={WebApp:{version:'9.6',initData:'test',viewportHeight:844,isFullscreen:true,safeAreaInset:{top:TOP,bottom:0},contentSafeAreaInset:{top:CONTENT,bottom:0},ready(){},expand(){},requestFullscreen(){},isVersionAtLeast(){return true},setHeaderColor(){},setBackgroundColor(){},setBottomBarColor(){},disableVerticalSwipes(){},onEvent(n,f){(window.tgEvents[n]??=[]).push(f)},BackButton:{hide(){},show(){},onClick(){}},checkHomeScreenStatus(){}}};".replace('TOP',str(20 if inset else 0)).replace('CONTENT',str(46 if inset else 0))
    return route.fulfill(body=sdk,content_type='text/javascript')
   if path.startswith('/claudex/api/'):
    requests.append((route.request.method,path))
    if path.endswith('/state'):
     data=state(engine);data.update(voice=True,voice_ready=True,job=livejob)
    elif path.endswith('/controls'):data={'state':state(engine),'text':'تنظیمات دستیار','text_fa':'تنظیمات دستیار','rows':[[{'action':'models','text':'Model'}]]}
    elif path.endswith('/usage'):data={'items':[{'title':'هفتگی','used':35,'left':'سه روز','at':'20:00'}],'ago':1}
    elif path.endswith('/ssh/servers'):data={'servers':[{'id':'local','name':'سرور محلی','host':'local','local':True},{'id':'panel','name':'پنل','host':'example.test','link':'https://panel.example/'}]}
    elif path.endswith('/send'):
     sendcount+=1;livejob={'id':'live-'+str(sendcount),'status':'done','text':'پاسخ تست','audio':'testaudio','audio_pending':False,'sid':'session-codex'};data={'job':livejob}
    elif path.endswith('/stt'):
     if failstt:return route.fulfill(status=500,json={'error':'test'})
     data={'text':'سلام آزمایشی'}
    elif path.endswith('/upload'):data={'image':'1234567890abcdef.jpg'}
    elif path.endswith('/session'):data=state(engine)
    elif path.endswith('/voice'):data={'voice':True}
    else:data={}
    return route.fulfill(json=data)
   file=root/('index.html' if path in ('/claudex/','/claudex') else path.removeprefix('/claudex/s/'))
   if file.is_file():return route.fulfill(body=file.read_bytes(),content_type=mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
   return route.fulfill(status=404)
  page.route('**/*',handle)
  page.add_init_script(r"""
window.mediaCalls=0;window.stops=0;window.played=0;window.denyMic=false;window.delayMic=0;
Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>{mediaCalls++;if(denyMic)throw new DOMException('denied','NotAllowedError');if(delayMic)await new Promise(r=>setTimeout(r,delayMic));return{getTracks:()=>[{stop(){stops++;}}]};}}});
window.AudioContext=class{constructor(){this.state='running';this.destination={};}resume(){return Promise.resolve()}close(){return Promise.resolve()}createMediaStreamSource(){return{connect(){},disconnect(){}}}createAnalyser(){let n=0;return{fftSize:1024,getFloatTimeDomainData(a){a.fill(n++<6?.1:0)}}}decodeAudioData(){return Promise.resolve({duration:.1})}createBufferSource(){return{connect(){},start(){played++;setTimeout(()=>this.onended?.(),100)},stop(){}}}};
window.MediaRecorder=class{static isTypeSupported(){return true}constructor(s,o){this.mimeType=o?.mimeType||'audio/mp4';this.state='inactive'}start(){this.state='recording'}stop(){this.state='inactive';this.ondataavailable?.({data:new Blob([new Uint8Array(1000)])});setTimeout(()=>this.onstop?.(),0)}};
""")
  page.goto('https://preview.test/claudex/');page.locator('[data-choose-engine=codex]').click();page.wait_for_selector('body.cx-mobile')
  page.locator('#cxVoice').click();page.wait_for_selector('#cxLive[data-phase=listening]')
  page.screenshot(path=str(out/'live-listening.png'))
  page.wait_for_function('window.played>=2',timeout=15000)
  assert sendcount>=2
  page.locator('#cxlEnd').click();assert page.locator('#cxLive').is_hidden()
  before=page.evaluate('mediaCalls');page.wait_for_timeout(700);assert page.evaluate('mediaCalls')==before
  assert not page.locator('#app').evaluate('(e)=>e.inert')
  page.evaluate('window.denyMic=true');page.locator('#cxVoice').click();page.wait_for_selector('#cxLive[data-phase=error]');assert 'اجازه' in page.locator('#cxlStatus').inner_text();page.locator('#cxlEnd').click()
  page.evaluate('window.denyMic=false;window.delayMic=600');page.locator('#cxVoice').click();page.wait_for_timeout(100);page.locator('#cxlEnd').click();before=page.evaluate('stops');page.wait_for_timeout(800);assert page.evaluate('stops')>before
  page.evaluate('window.delayMic=0');failstt=True;page.locator('#cxVoice').click();page.wait_for_selector('#cxLive[data-phase=error]',timeout=7000);page.locator('#cxlEnd').click();failstt=False
  assert not errors,errors
  browser.close()
print('PASS two automatic spoken turns; stop cleanup; denied mic; late permission cleanup; STT failure')
