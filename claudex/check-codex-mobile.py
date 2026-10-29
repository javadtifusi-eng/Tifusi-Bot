from pathlib import Path
from urllib.parse import urlparse,parse_qs
import mimetypes,json
from playwright.sync_api import sync_playwright
import os,tempfile
root=Path(os.environ.get('CLODEX_STATIC',str(Path(__file__).parent/'static')));out=Path(tempfile.mkdtemp(prefix='codex-mobile-preview-'))
state=lambda engine:dict(current='session-'+engine,model='opus' if engine=='claude' else 'gpt-6',models=[{'id':'opus','label':'Opus'},{'id':'gpt-6','label':'GPT-6'}],sessions=[{'id':'session-'+engine,'title':'گفتگوی آزمایشی'}],voice=True,job=None,history=[{'role':'user','text':'سلام، ظاهر جدید آماده است؟'},{'role':'assistant','text':'بله، طرح تازه آماده است.\n\n```sh\nprintf hello\n```'}])
base_state=state
removed=set()
selected_model='gpt-6'
selected_effort='medium'
def state(engine):
 d=base_state(engine)
 if engine=='codex':d.update(model=selected_model,preferences={'effort':selected_effort})
 if engine=='codex':d['sessions'].append({'id':'second','title':'دوم'})
 d['sessions']=[x for x in d['sessions'] if x['id'] not in removed]
 if d['current'] in removed:d.update(current=None,history=[])
 return d
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 for width,inset in [(320,66),(390,66),(390,0),(440,66),(1280,66)]:
  removed.clear()
  selected_model='gpt-6';selected_effort='medium'
  context=browser.new_context(viewport={'width':width,'height':844},permissions=['clipboard-read','clipboard-write'])
  page=context.new_page();errors=[];requests=[];events=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  def handle(route):
   global selected_model,selected_effort
   path=urlparse(route.request.url).path;engine='codex' if '/codex/' in path else 'claude'
   if path=='/claudex/s/telegram-web-app.js':
    sdk="window.tgEvents={};window.Telegram={WebApp:{version:'9.6',initData:'test',viewportHeight:844,isFullscreen:true,safeAreaInset:{top:TOP,bottom:0},contentSafeAreaInset:{top:CONTENT,bottom:0},ready(){},expand(){},requestFullscreen(){},isVersionAtLeast(){return true},setHeaderColor(){},setBackgroundColor(){},setBottomBarColor(){},disableVerticalSwipes(){},onEvent(n,f){(window.tgEvents[n]??=[]).push(f)},BackButton:{hide(){},show(){},onClick(){}},checkHomeScreenStatus(){}}};".replace('TOP',str(20 if inset else 0)).replace('CONTENT',str(46 if inset else 0))
    return route.fulfill(body=sdk,content_type='text/javascript')
   if path.startswith('/claudex/api/'):
    requests.append((route.request.method,path))
    if path.endswith('/state'):data=state(engine)
    elif path.endswith('/controls'):
     action=route.request.post_data_json['action']
     if action.startswith('model:'):selected_model=action.split(':',1)[1]
     if action.startswith('thinking:'):selected_effort=action.split(':',1)[1]
     rows=[[{'action':'model:gpt-6-sol','text':'GPT-6 Sol'}]] if action=='models' else [[{'action':'thinking:low','text':'Fast'}]] if action=='set:effort' else []
     rows.append([{'action':'models','text':'Model'}])
     data={'state':state(engine),'text':'تنظیمات دستیار','text_fa':'تنظیمات دستیار','rows':rows}
    elif path.endswith('/usage'):data={'items':[{'title':'هفتگی','used':35,'left':'سه روز','at':'20:00'}],'ago':1}
    elif path.endswith('/ssh/servers'):data={'servers':[{'id':'local','name':'سرور محلی','host':'local','local':True},{'id':'panel','name':'پنل','host':'example.test','link':'https://panel.example/'}]}
    elif path.endswith('/send'):data={'job':{'id':'job-preview','status':'running','progress':'در حال بررسی','elapsed':2}}
    elif path.endswith('/upload'):data={'image':'1234567890abcdef.jpg'}
    elif path.endswith('/session'):
     b=route.request.post_data_json
     if b.get('action')=='delete':
      if not b.get('confirmation'):return route.fulfill(json={'confirmation':'test-confirmation'})
      assert b['confirmation']=='test-confirmation'
      removed.add(b['sid'])
     data=state(engine)
    elif path.endswith('/voice'):data={'voice':True}
    else:data={}
    return route.fulfill(json=data)
   file=root/('index.html' if path in ('/claudex/','/claudex') else path.removeprefix('/claudex/s/'))
   if file.is_file():return route.fulfill(body=file.read_bytes(),content_type=mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
   return route.fulfill(status=404)
  page.route('**/*',handle)
  page.goto('https://preview.test/claudex/');page.wait_for_selector('#workspaceDock');page.evaluate('document.fonts.ready')
  assert page.locator('#fsdebug').count()==0
  assert page.locator('#workspaceDock button').count()==5
  assert page.locator('#workspaceDock').is_visible()
  minimum=74 if inset else 56
  assert page.locator('.home-brand').bounding_box()['y']>=minimum
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.wait_for_timeout(300);page.screenshot(path=str(out/f'home-{width}-{inset}.png'))
  page.locator('[data-choose-engine=codex]').click();page.wait_for_selector('body.cx-mobile')
  assert page.locator('#workspaceDock').is_hidden()
  assert page.locator('#cxHeader').bounding_box()['y']>=minimum
  assert page.locator('#cxHeader').is_visible()
  assert page.locator('#chat .msg.bot .hid').is_visible()
  assert page.locator('#chat .msg.bot .show').count()==0
  assert page.locator('#cxVoice').is_visible()  # Voice loop has a dedicated media test.
  page.locator('#input').fill('پیش‌نویس کدکس')
  page.wait_for_timeout(300);page.screenshot(path=str(out/f'chat-{width}-{inset}.png'))
  page.locator('[data-cx="copy:1"]').click();assert 'printf hello' in page.evaluate('navigator.clipboard.readText()')
  page.locator('#cxHeader [data-cx=sidebar]').click();page.wait_for_selector('#cxDrawer:not([hidden])')
  page.locator('#cxSearch').fill('گفتگوی');assert page.locator('.cx-session').count()==1
  page.locator('#cxSearch').fill('بدون نتیجه');assert page.locator('.cx-session').count()==0
  page.locator('#cxSearch').fill('')
  page.wait_for_timeout(300);page.screenshot(path=str(out/f'sidebar-{width}-{inset}.png'))
  assert page.locator('.cx-session-more').count()==2
  page.locator('[data-cx="session-menu:second"]').click();page.locator('[data-cx=delete-selected]').click()
  page.wait_for_timeout(100);page.screenshot(path=str(out/f'delete-{width}-{inset}.png'))
  assert 'second' not in removed
  page.locator('[data-cx=confirm-delete]').click();page.wait_for_selector('#cxDrawer:not([hidden])')
  assert 'second' in removed
  assert page.locator('.cx-session').count()==1
  assert page.evaluate('S.data.codex.current')=='session-codex'
  assert page.locator('#input').input_value()=='پیش‌نویس کدکس'
  page.locator('.cx-session').dispatch_event('contextmenu');page.locator('[data-cx=delete-selected]').click();page.locator('[data-cx=cancel-delete]').click();page.wait_for_selector('#cxDrawer:not([hidden])')
  assert 'session-codex' not in removed
  page.locator('.cx-profile').click();page.wait_for_selector('[data-cx=appearance]')
  page.wait_for_timeout(300);page.screenshot(path=str(out/f'settings-{width}-{inset}.png'))
  page.locator('[data-cx=appearance]').click();page.locator('[data-cx="theme:light"]').click()
  assert page.locator('body').get_attribute('data-cx-theme')=='light'
  page.locator('#sheetClose').click();page.wait_for_timeout(300);page.screenshot(path=str(out/f'light-{width}-{inset}.png'))
  assert page.locator('#input').input_value()=='پیش‌نویس کدکس'
  assert page.locator('#row #cxComposerModel').is_visible() and page.locator('#row #cxComposerSpeed').is_visible()
  page.locator('#cxComposerModel').click();page.wait_for_selector('[data-control="model:gpt-6-sol"]');page.locator('[data-control="model:gpt-6-sol"]').click();page.wait_for_function("document.querySelector('#cxComposerModel').textContent.includes('gpt-6-sol')")
  page.locator('#sheetClose').click()
  page.locator('#cxComposerSpeed').click();page.wait_for_selector('[data-control="thinking:low"]');page.locator('[data-control="thinking:low"]').click();page.wait_for_function("document.querySelector('#cxComposerSpeed').textContent.includes('سریع')")
  page.locator('#sheetClose').click();assert page.locator('#input').input_value()=='پیش‌نویس کدکس'
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.screenshot(path=str(out/f'composer-{width}-{inset}.png'))
  page.locator('#cxHeader [data-cx=models]').click();page.wait_for_selector('[data-control=models]')
  page.locator('#sheetClose').click()
  page.locator('#cxHeader [data-cx=more]').click();page.locator('#sheetContent [data-cx=settings]').click()
  page.locator('[data-cx=voice]').click();page.wait_for_timeout(100)
  assert any(path.endswith('/voice') for method,path in requests)
  page.locator('[data-cx=language]').click()
  assert page.locator('html').get_attribute('dir')=='ltr'
  page.locator('[data-cx=language]').click()
  page.locator('[data-cx=appearance]').click();page.locator('[data-cx="theme:dark"]').click();page.locator('#sheetClose').click()
  page.evaluate("Object.defineProperty(window.visualViewport,'height',{configurable:true,get:()=>420});syncSshViewport()")
  page.wait_for_timeout(100)
  composer=page.locator('.composer').bounding_box();assert composer['y']+composer['height']<=425,composer
  page.evaluate("delete window.visualViewport.height;syncSshViewport()")
  page.evaluate('S.msgs.codex=[];render.key=null;render()')
  page.locator('#input').fill('');page.evaluate('autosize()')
  page.screenshot(path=str(out/f'empty-{width}-{inset}.png'))
  assert page.locator('.cx-suggestions button').count()==3
  page.locator('.cx-suggestions button').first.click();assert page.locator('#input').input_value()
  page.locator('#file').set_input_files({'name':'sample.jpg','mimeType':'image/jpeg','buffer':b'preview-only'})
  page.wait_for_timeout(200)
  assert any(path.endswith('/upload') for method,path in requests)
  page.locator('#input').fill('پیام آزمایشی در محیط ایزوله');page.locator('#btnSend').click();page.wait_for_timeout(100)
  assert any(path.endswith('/codex/send') for method,path in requests)
  page.evaluate('S.data.codex.job=null')
  page.locator('#cxHeader [data-cx=sidebar]').click();page.wait_for_selector('#cxDrawer:not([hidden])')
  page.locator('[data-cx="session-menu:session-codex"]').click();page.locator('[data-cx=delete-selected]').click();page.locator('[data-cx=confirm-delete]').click();page.wait_for_selector('#cxDrawer:not([hidden])')
  assert 'session-codex' in removed
  assert page.evaluate('S.data.codex.current') is None
  assert page.evaluate('S.msgs.codex.length')==0
  page.locator('#cxDrawer [data-cx=home]').click()
  assert not page.locator('body').evaluate('(e)=>e.classList.contains("cx-mobile")')
  assert page.locator('#workspaceDock').is_visible()
  assert page.locator('#engineHome').is_visible()
  page.locator('#homeSsh').click();page.wait_for_selector('.xterm');assert page.locator('#cxHeader').is_hidden()
  assert page.locator('#workspaceDock').is_visible()
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  assert not errors,errors
  context.close()
 browser.close()
print('PASS mobile layout, sidebar/search, themes, settings/model/voice/language, clipboard, mock upload/send, keyboard, home/SSH, no JS errors')
