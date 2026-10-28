from pathlib import Path
from urllib.parse import urlparse,parse_qs
import mimetypes,json
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent/'static';out=Path('/root/backups/claudex-ui-check');out.mkdir(parents=True,exist_ok=True)
state=lambda engine:dict(current='session-'+engine,model='opus' if engine=='claude' else 'gpt-6',models=[{'id':'opus','label':'Opus'},{'id':'gpt-6','label':'GPT-6'}],sessions=[{'id':'session-'+engine,'title':'گفتگوی آزمایشی'}],voice=False,job=None,history=[{'role':'user','text':'سلام، ظاهر جدید آماده است؟'},{'role':'assistant','text':'بله، طرح تازه آماده است.\n\n```sh\nprintf hello\n```'}])
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 for width,inset in [(320,66),(390,66),(390,0),(1280,66)]:
  context=browser.new_context(viewport={'width':width,'height':844},permissions=['clipboard-read','clipboard-write'])
  page=context.new_page();errors=[];requests=[];events=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  def handle(route):
   path=urlparse(route.request.url).path;engine='codex' if '/codex/' in path else 'claude'
   if path=='/claudex/s/telegram-web-app.js':
    sdk="window.tgEvents={};window.Telegram={WebApp:{version:'9.6',initData:'test',viewportHeight:844,isFullscreen:true,safeAreaInset:{top:TOP,bottom:0},contentSafeAreaInset:{top:CONTENT,bottom:0},ready(){},expand(){},requestFullscreen(){},isVersionAtLeast(){return true},setHeaderColor(){},setBackgroundColor(){},setBottomBarColor(){},disableVerticalSwipes(){},onEvent(n,f){(window.tgEvents[n]??=[]).push(f)},BackButton:{hide(){},show(){},onClick(){}},checkHomeScreenStatus(){}}};".replace('TOP',str(20 if inset else 0)).replace('CONTENT',str(46 if inset else 0))
    return route.fulfill(body=sdk,content_type='text/javascript')
   if path.startswith('/claudex/api/'):
    requests.append((route.request.method,path))
    if path.endswith('/state'):data=state(engine)
    elif path.endswith('/controls'):data={'state':state(engine),'text':'تنظیمات دستیار','text_fa':'تنظیمات دستیار','rows':[[{'action':'models','text':'Model'}]]}
    elif path.endswith('/usage'):data={'items':[{'title':'هفتگی','used':35,'left':'سه روز','at':'20:00'}],'ago':1}
    elif path.endswith('/ssh/servers'):data={'servers':[{'id':'local','name':'سرور محلی','host':'local','local':True},{'id':'panel','name':'پنل','host':'example.test','link':'https://panel.example/'}]}
    elif path.endswith('/send'):data={'job':'new'}
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
  page.screenshot(path=str(out/f'home-{width}-{inset}.png'))
  page.locator('#workspaceDock [data-dock=codex]').click();page.wait_for_selector('body[data-tab=codex][data-view=chat]')
  assert page.locator('.top').bounding_box()['y']>=minimum
  assert page.locator('.composer').bounding_box()['y']+page.locator('.composer').bounding_box()['height']<=page.locator('#workspaceDock').bounding_box()['y']
  page.locator('#input').fill('پیش‌نویس کدکس')
  page.locator('#workspaceDock [data-dock=claude]').click();page.wait_for_selector('body[data-tab=claude]')
  page.locator('#input').fill('پیش‌نویس کلاد')
  page.locator('#workspaceDock [data-dock=codex]').click();assert page.locator('#input').input_value()=='پیش‌نویس کدکس'
  page.locator('#chat .copy-code').first.click();assert 'printf hello' in page.evaluate('navigator.clipboard.readText()')
  page.screenshot(path=str(out/f'chat-{width}-{inset}.png'))
  page.locator('#btnSessions').click();page.wait_for_selector('#sheet:not(.hidden) .item')
  page.locator('#sheetClose').click();assert page.locator('#sheet').is_hidden()
  page.locator('#workspaceDock [data-dock=settings]').click();page.wait_for_selector('.control-row button')
  assert page.locator('#workspaceDock').is_visible()
  page.screenshot(path=str(out/f'settings-{width}-{inset}.png'))
  page.locator('#workspaceDock [data-dock=claude]').click();page.wait_for_selector('body[data-tab=claude][data-view=chat]')
  assert page.locator('#sheet').is_hidden()
  page.locator('#workspaceDock [data-dock=ssh]').click();page.wait_for_selector('.xterm')
  assert page.locator('.top').bounding_box()['y']>=minimum
  assert page.locator('.term-wrap').bounding_box()['height']>150
  assert page.locator('.term-wrap').bounding_box()['y']+page.locator('.term-wrap').bounding_box()['height']<=page.locator('#workspaceDock').bounding_box()['y']+2
  page.screenshot(path=str(out/f'ssh-{width}-{inset}.png'))
  page.locator('#termKeys').click();page.wait_for_selector('[data-ssh-go]')
  page.locator('#sheetClose').click()
  page.locator('#workspaceDock [data-dock=codex]').click()
  # Simulate visual viewport shrinking under the on-screen keyboard without changing fullscreen insets.
  page.evaluate("Object.defineProperty(window.visualViewport,'height',{configurable:true,get:()=>420});syncSshViewport()")
  page.wait_for_timeout(60);assert page.locator('#workspaceDock').is_hidden()
  assert page.locator('.composer').bounding_box()['y']+page.locator('.composer').bounding_box()['height']<=425
  page.evaluate("delete window.visualViewport.height;syncSshViewport()")
  page.wait_for_timeout(60);assert page.locator('#workspaceDock').is_visible()
  page.locator('#workspaceDock [data-dock=home]').click();page.wait_for_selector('body[data-view=home]')
  page.locator('#workspaceDock [data-dock=settings]').click();page.wait_for_selector('.control-row button');page.locator('#sheetClose').click()
  assert page.locator('body').get_attribute('data-view')=='home'
  assert not errors,errors
  context.close()
 browser.close()
print('PASS: 320/390/1280, fullscreen with/without insets, home/dock, drafts, copy, sessions/settings, SSH layout, keyboard, no JS errors')
