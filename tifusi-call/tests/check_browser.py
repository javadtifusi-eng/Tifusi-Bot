import json,time,os
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=os.environ.get('CALL_TEST_URL','http://127.0.0.1:8093/call/')
OUT=Path(os.environ.get('CALL_TEST_OUTPUT','/tmp/tifusi-call-preview'));OUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required'])
 contexts=[];errors=[]
 def tab(width=390):
  context=browser.new_context(viewport={'width':width,'height':844},permissions=['camera','microphone','clipboard-read','clipboard-write']);contexts.append(context);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));return page
 host=tab();host.goto(BASE+'?relay=1');host.evaluate('document.fonts.ready');host.screenshot(path=str(OUT/'home390.png'),full_page=True)
 host.locator('#name').fill('جواد');host.locator('#startButton').click();host.wait_for_selector('#call:not([hidden])');invite=host.evaluate('inviteURL()');assert invite.startswith(BASE)
 guest=tab();guest.goto(invite.replace('#','?relay=1#'));guest.locator('#name').fill('رفیق');guest.locator('#startButton').click()
 for page in [host,guest]:page.wait_for_function("C.pc?.connectionState==='connected'",timeout=40000)
 for page in [host,guest]:page.wait_for_function("document.getElementById('remoteVideo').videoWidth>0 && !document.getElementById('remotePlaceholder').hidden===false",timeout=12000)
 host.wait_for_timeout(1500)
 def stats(page):
  return page.evaluate("""async()=>{let result={video:0,audio:0,relay:false};const stats=await C.pc.getStats();stats.forEach(s=>{if(s.type==='inbound-rtp'&&s.kind==='video')result.video+=s.framesDecoded||0;if(s.type==='inbound-rtp'&&s.kind==='audio')result.audio+=s.bytesReceived||0;if(s.type==='candidate-pair'&&s.nominated&&s.state==='succeeded')result.relay=stats.get(s.localCandidateId)?.candidateType==='relay';});return result;}""")
 for page in [host,guest]:
  s=stats(page);assert s['video']>0 and s['audio']>0 and s['relay'],s
 host.screenshot(path=str(OUT/'connected390.png'),full_page=True)
 host.locator('#micButton').click();assert host.evaluate('!C.stream.getAudioTracks()[0].enabled');guest.wait_for_function('!C.peerMic')
 host.locator('#cameraButton').click();guest.wait_for_function('!C.peerCamera');assert host.evaluate('C.stream.getVideoTracks().length===0')
 host.locator('#cameraButton').click();guest.wait_for_function('C.peerCamera');guest.wait_for_function("document.getElementById('remoteVideo').videoWidth>0")
 # Reject a third participant while preserving the original pair.
 third=tab();third.goto(invite);third.locator('#startButton').click();third.wait_for_selector('#ended:not([hidden])',timeout=15000);assert 'دستگاه دیگری' in third.locator('#endText').inner_text();assert host.evaluate("C.pc.connectionState==='connected'") and guest.evaluate("C.pc.connectionState==='connected'")
 # Re-establish signaling and media without creating another room.
 host.evaluate('C.ws.close()');guest.wait_for_function("C.pc===null",timeout=7000)
 for page in [host,guest]:page.wait_for_function("C.pc?.connectionState==='connected'",timeout=25000)
 for page in [host,guest]:assert stats(page)['relay']
 host.locator('#endButton').click();guest.wait_for_selector('#ended:not([hidden])');assert host.evaluate('C.stream===null && C.pc===null');assert guest.evaluate('C.stream===null && C.pc===null')
 # Audio only does not request/keep a video track.
 a=tab();a.goto(BASE);a.locator('.mode-switch label').nth(1).click();a.locator('#startButton').click();a.wait_for_selector('#call:not([hidden])');assert a.evaluate('C.stream.getVideoTracks().length===0');b=tab();b.goto(a.evaluate('inviteURL()'));b.locator('.mode-switch label').nth(1).click();b.locator('#startButton').click()
 for page in [a,b]:page.wait_for_function("C.pc?.connectionState==='connected'",timeout=25000);assert page.evaluate('C.stream.getVideoTracks().length===0')
 a.locator('#endButton').click();b.wait_for_selector('#ended:not([hidden])')
 for width in [320,440,1280]:
  page=tab(width);page.goto(BASE);page.evaluate('document.fonts.ready');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(OUT/f'home{width}.png'),full_page=True)
 assert not errors,errors
 for context in contexts:context.close()
 browser.close()
print('PASS real WebRTC audio+video through forced TURN relay, controls, two-person limit, reconnection, hangup, audio-only and responsive layouts')
