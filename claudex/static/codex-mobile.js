'use strict';
// ChatGPT-inspired mobile presentation. Existing Codex transport remains authoritative.
(()=>{
 const fa=()=>uiLanguage==='fa', label=(a,b)=>fa()?a:b;
 const paths={menu:'M4 8h16M4 16h10',new:'M13 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-8M10 14l1-4L19 2l3 3-8 8z',more:'M5 12h.01M12 12h.01M19 12h.01',close:'M6 6l12 12M6 18 18 6',plus:'M12 4v16M4 12h16',arrow:'M12 20V4M5 11l7-7 7 7',copy:'M8 8h12v12H8zM16 8V4H4v12h4',speaker:'M11 4 5 9H2v6h3l6 5zM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14',share:'M12 16V2M7 7l5-5 5 5M5 12v9h14v-9',home:'m3 10 9-7 9 7v11h-6v-7H9v7H3z',search:'M20 20l-5-5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2',chevron:'m9 5 7 7-7 7',wave:'M4 9v6M8 6v12M12 3v18M16 6v12M20 9v6'};
 Object.assign(paths,{globe:'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2c-6 6-6 14 0 20M12 2c6 6 6 14 0 20',palette:'M12 3a9 9 0 1 0 0 18h2a2 2 0 0 0 0-4h-1a2 2 0 0 1 0-4h4a4 4 0 0 0 4-4c0-4-5-6-9-6M7 8h.01M11 6h.01M16 7h.01M6 13h.01',usage:'M4 20V10h3v10M10 20V4h3v16M16 20v-7h3v7',chat:'M3 4h18v13H9l-6 4zM7 9h10M7 13h6',model:'M12 3l3 6 6 3-6 3-3 6-3-6-6-3 6-3z'});
 const icon=k=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+paths[k]+'"/></svg>';
 const button=(action,k,title,extra='')=>'<button type="button" data-cx="'+action+'" aria-label="'+esc(title)+'" '+extra+'>'+icon(k)+'</button>';
 const header=document.createElement('header');header.id='cxHeader';header.innerHTML=button('sidebar','menu','گفتگوها')+'<button type="button" data-cx="models" class="cx-title"><b>ChatGPT</b><span>Codex <i>⌄</i></span></button><div class="cx-header-end">'+button('new','new','گفتگوی جدید')+button('more','more','گزینه‌ها')+'</div>';
 $('#app').prepend(header);
 const drawer=document.createElement('div');drawer.id='cxDrawer';drawer.hidden=true;drawer.innerHTML='<button class="cx-scrim" data-cx="close" aria-label="بستن منو"></button><aside role="dialog" aria-modal="true" aria-label="گفتگوها"><div class="cx-drawer-top">'+button('close','menu','بستن منو')+button('new','new','گفتگوی جدید')+'</div><label class="cx-search">'+icon('search')+'<input id="cxSearch" type="search" placeholder="جستجوی گفتگوها"></label><button class="cx-nav-row" data-cx="new">'+icon('new')+'<span data-cx-label="new"></span></button><button class="cx-nav-row" data-cx="home">'+icon('home')+'<span data-cx-label="home"></span></button><p class="cx-section" data-cx-label="recent"></p><div id="cxSessions"></div><button class="cx-profile" data-cx="settings"><span class="cx-avatar">J</span><span><b>'+label('جواد','Javad')+'</b><small>Codex</small></span>'+icon('settings')+'</button></aside>';
 document.body.append(drawer);
 let mode=localStorage.getItem('cx-appearance')||'dark',accent=localStorage.getItem('cx-accent')||'default';
 const colors={default:'',blue:'#d6e9ff',green:'#d7efdf',yellow:'#fff0bd',pink:'#f9d9ec',orange:'#ffdfc6',purple:'#e9ddff'};
 const media=matchMedia('(prefers-color-scheme: dark)');
 const active=()=>S.tab==='codex'&&view!=='home';
 function theme(){document.body.dataset.cxTheme=mode==='system'?(media.matches?'dark':'light'):mode;document.body.style.setProperty('--cx-accent-bubble',colors[accent]||'var(--cx-user)');}
 media.addEventListener?.('change',theme);theme();
 let wasActive=false;
 const previousNav=setNav;
 setNav=function(){previousNav();const on=active();document.body.classList.toggle('cx-mobile',on);if(!on){drawer.hidden=true;if(wasActive)try{tg?.setHeaderColor('#200e16');tg?.setBackgroundColor('#200e16');}catch{}}wasActive=on;
  header.querySelector('.cx-title span').textContent=(S.data.codex?.model||'Codex')+' ⌄';
  $('#cxSearch').placeholder=label('جستجوی گفتگوها','Search chats');
  drawer.querySelector('[data-cx-label=new]').textContent=label('گفتگوی جدید','New chat');drawer.querySelector('[data-cx-label=home]').textContent=label('خانهٔ تیفوسی','Tifusi home');drawer.querySelector('[data-cx-label=recent]').textContent=label('گفتگوهای اخیر','Recent chats');
  if(on){$('#input').placeholder=label('هر چیزی بپرس','Ask anything');try{const bg=document.body.dataset.cxTheme==='dark'?'#212121':'#ffffff';tg?.setHeaderColor(bg);tg?.setBackgroundColor(bg);}catch{}}
 };
 const oldRender=render;
 render=function(){oldRender();if(!active())return;syncComposerControls();const empty=$('#chat .empty');if(empty)empty.innerHTML='<h2>'+label('از کجا شروع کنیم؟','What can I help with?')+'</h2><div class="cx-suggestions"><button data-cx="suggest" data-prompt="برای امروز یک برنامهٔ عملی و کوتاه پیشنهاد بده">'+label('برنامه‌ریزی روز','Make a plan')+'</button><button data-cx="suggest" data-prompt="کمکم کن ایده‌ام را به یک پروژهٔ قابل اجرا تبدیل کنم">'+label('پرورش یک ایده','Brainstorm')+'</button><button data-cx="suggest" data-prompt="برای بررسی و اصلاح کدم کمک می‌خواهم">'+label('کمک با کد','Help me code')+'</button></div>';};
 const oldBubble=bubble;
 bubble=function(m,i){const el=oldBubble(m,i);if(S.tab==='codex'&&m.role!=='user'){const transcript=el.querySelector(':scope > .hid');if(transcript){transcript.classList.remove('hidden');el.querySelector(':scope > .voice')?.remove();el.querySelector(':scope > .show')?.remove();}const bar=document.createElement('div');bar.className='cx-response-actions';bar.innerHTML=button('copy:'+i,'copy',label('کپی پاسخ','Copy response'))+button('read:'+i,'speaker',label('خواندن پاسخ','Read aloud'))+button('share:'+i,'share',label('اشتراک پاسخ','Share response'));el.append(bar);}return el;};
 function closeDrawer(){drawer.hidden=true;$('#app').inert=false;header.querySelector('[data-cx=sidebar]').focus({preventScroll:true});}
 function drawSessions(){const q=$('#cxSearch').value.trim().toLocaleLowerCase();const list=(S.data.codex?.sessions||[]).filter(s=>(s.title||s.id).toLocaleLowerCase().includes(q));$('#cxSessions').innerHTML=list.map(s=>'<div class="cx-session-row '+(s.id===S.data.codex?.current?'selected':'')+'"><button class="cx-session" data-cx-session="'+esc(s.id)+'">'+esc(s.title||label('گفتگوی بدون عنوان','Untitled chat'))+'</button><button class="cx-session-more" data-cx="session-menu:'+esc(s.id)+'" aria-label="'+label('گزینه‌های گفتگو','Chat options')+'">'+icon('more')+'</button></div>').join('')||'<p class="cx-muted">'+label('گفتگویی پیدا نشد','No chats found')+'</p>';}
 async function sidebar(){drawer.hidden=false;$('#app').inert=true;drawSessions();$('#cxSearch').focus({preventScroll:true});try{await refresh('codex',false);if(!drawer.hidden)drawSessions();}catch{toast(tr('failed'));}}
 $('#cxSearch').oninput=drawSessions;
 const oldClose=closeSheet;closeSheet=function(){oldClose();delete $('#sheet').dataset.cxPage;};
 const oldSheet=sheet;sheet=function(content){delete $('#sheet').dataset.cxPage;oldSheet(content);};
 function page(title,html,type='settings'){view='settings';setNav();sheet('<h3>'+title+'</h3>'+html);$('#sheet').dataset.cxPage=type;}
 const row=(action,title,value='',key=({language:'globe',accent:'palette',usage:'usage',models:'model',manage:'chat','control:tones':'chat'})[action]||'settings')=>'<button type="button" class="cx-setting" data-cx="'+action+'">'+icon(key)+'<span>'+title+'</span><small>'+esc(value)+'</small>'+icon('chevron')+'</button>';
 function settings(){const p=S.data.codex?.preferences||{};page(label('تنظیمات','Settings'),'<div class="cx-settings-profile"><span class="cx-avatar">J</span><b>'+label('جواد · کدکس','Javad · Codex')+'</b></div><p class="cx-section">'+label('شخصی‌سازی','Personalization')+'</p><div class="cx-group">'+row('control:tones',label('لحن گفتگو','Conversation tone'),localized(p.tone||'Warm'))+row('native',label('تنظیمات دستیار','Assistant settings'))+'</div><p class="cx-section">'+label('ظاهر','Theme')+'</p><div class="cx-group">'+row('appearance',label('حالت نمایش','Appearance'),label(({dark:'تیره',light:'روشن',system:'سیستم'})[mode],mode))+row('accent',label('رنگ تأکیدی','Accent color'))+'</div><p class="cx-section">'+label('تنظیمات برنامه','App settings')+'</p><div class="cx-group">'+row('language',label('زبان برنامه','App language'),label('فارسی','English'))+row('voice',label('پاسخ صوتی','Voice replies'),S.data.codex?.voice?label('روشن','On'):label('خاموش','Off'),'wave')+row('usage',label('میزان مصرف','Usage'))+row('models',label('مدل','Model'),S.data.codex?.model||'Default')+'</div><p class="cx-section">'+label('گفتگوها','Conversations')+'</p><div class="cx-group">'+row('export',label('دریافت متن این گفتگو','Export this conversation'),'','share')+row('manage',label('مدیریت گفتگوها','Manage chats'))+row('home',label('بازگشت به خانهٔ تیفوسی','Back to Tifusi home'),'','home')+'</div>');}
 function appearance(){page(label('حالت نمایش','Appearance'),'<div class="cx-group">'+['system','light','dark'].map(k=>row('theme:'+k,label(({system:'همراه دستگاه',light:'روشن',dark:'تیره'})[k],k),mode===k?'✓':'')).join('')+'</div>');}
 function accents(){page(label('رنگ تأکیدی','Accent color'),'<div class="cx-group">'+Object.keys(colors).map((k,i)=>row('accent:'+k,label(['پیش‌فرض','آبی','سبز','زرد','صورتی','نارنجی','بنفش'][i],k),accent===k?'✓':'')).join('')+'</div>');}
 function more(){page(label('گزینه‌های گفتگو','Chat options'),'<div class="cx-group">'+row('new',label('گفتگوی جدید','New chat'),'','new')+row('models',label('انتخاب مدل','Choose model'))+row('settings',label('تنظیمات','Settings'))+row('export',label('دریافت متن گفتگو','Export conversation'),'','share')+row('delete',label('حذف این گفتگو','Delete conversation'))+row('home',label('خانهٔ تیفوسی','Tifusi home'),'','home')+'</div>','menu');}
 function exportChat(){const text=(S.msgs.codex||[]).map(m=>(m.role==='user'?label('شما','You'):'Codex')+'\n'+m.text).join('\n\n');const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='codex-conversation.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
 let deleteTarget=null,holdTimer=null,held=false,holdStart=null;
 function sessionMenu(sid){
  const item=S.data.codex?.sessions.find(x=>x.id===sid);if(!item)return;
  deleteTarget=sid;closeDrawer();page(label('گزینه‌های گفتگو','Chat options'),'<p class="cx-selected-title">'+esc(item.title||label('گفتگوی بدون عنوان','Untitled chat'))+'</p><div class="cx-group">'+row('delete-selected',label('حذف گفتگو','Delete chat'),'','close')+'</div>','menu');
 }
 function confirmDelete(){const item=S.data.codex?.sessions.find(x=>x.id===deleteTarget);if(!item)return;
  page(label('این گفتگو حذف شود؟','Delete this chat?'),'<p class="cx-delete-description">'+esc(item.title||label('گفتگوی بدون عنوان','Untitled chat'))+'</p><div class="cx-delete-actions"><button data-cx="cancel-delete">'+label('انصراف','Cancel')+'</button><button class="cx-danger" data-cx="confirm-delete">'+label('حذف گفتگو','Delete chat')+'</button></div>','confirm');
 }
 const cancelHold=()=>{clearTimeout(holdTimer);holdTimer=null;};
 drawer.addEventListener('pointerdown',e=>{const b=e.target.closest('[data-cx-session]');if(!b)return;held=false;holdStart={x:e.clientX,y:e.clientY};holdTimer=setTimeout(()=>{held=true;sessionMenu(b.dataset.cxSession);},500);});
 drawer.addEventListener('pointermove',e=>{if(holdStart&&Math.hypot(e.clientX-holdStart.x,e.clientY-holdStart.y)>10)cancelHold();});
 for(const event of ['pointerup','pointercancel','scroll'])drawer.addEventListener(event,cancelHold,true);
 drawer.addEventListener('contextmenu',e=>{const b=e.target.closest('[data-cx-session]');if(b){e.preventDefault();cancelHold();held=true;sessionMenu(b.dataset.cxSession);}});
 document.addEventListener('click',e=>{if(held&&e.target.closest('[data-cx-session]')){held=false;e.preventDefault();e.stopImmediatePropagation();}},true);
 let actionBusy=false;
 document.addEventListener('click',async e=>{
  const session=e.target.closest('[data-cx-session]');const b=e.target.closest('[data-cx]');if(!active()||(!b&&!session))return;
  e.preventDefault();if(actionBusy)return;
  const action=b?.dataset.cx||'';
  try{
   if(session){actionBusy=true;await sessionAction({action:'open',sid:session.dataset.cxSession});closeDrawer();closeSheet();return;}
   if(action.startsWith('session-menu:'))return sessionMenu(action.slice(13));
   if(action==='delete-selected')return confirmDelete();
   if(action==='cancel-delete'){closeSheet();return await sidebar();}
   if(action==='confirm-delete'){
    const sid=deleteTarget;if(!sid)return;
    const job=S.data.codex?.job;if(job?.status==='running'&&(job.sid===sid||S.data.codex.current===sid))return toast(label('این گفتگو هنوز مشغول کار است؛ بعد از پایانش حذف کن.','Wait for this chat to finish before deleting it.'));
    actionBusy=true;await sessionAction({action:'delete',sid});deleteTarget=null;closeSheet();await sidebar();return;
   }
   if(action==='close')return closeDrawer();
   if(action==='sidebar')return await sidebar();
   if(!drawer.hidden)closeDrawer();
   if(action==='home'){closeSheet();showAssistantHome();return;}
   if(action==='new'){actionBusy=true;await sessionAction({action:'new'});drafts.codex='';$('#input').value='';autosize();closeSheet();render();return;}
   if(action==='settings')return settings();if(action==='more')return more();if(action==='appearance')return appearance();if(action==='accent')return accents();
   if(action.startsWith('theme:')){mode=action.split(':')[1];localStorage.setItem('cx-appearance',mode);theme();setNav();return appearance();}
   if(action.startsWith('accent:')){accent=action.split(':')[1];localStorage.setItem('cx-accent',accent);theme();return accents();}
   if(action==='voice-screen'){page(label('صدا','Voice'),'<div class="cx-voice-intro"><div class="cx-orb"></div><p>'+label('پیام صوتی ضبط کن؛ بعد از ارسال، پاسخ را بشنو.','Record a voice message, then listen to the reply.')+'</p></div><div class="cx-group">'+row('record',label('ضبط پیام صوتی','Record a voice message'),'','wave')+row('voice',label('پاسخ صوتی','Voice replies'),S.data.codex?.voice?label('روشن','On'):label('خاموش','Off'),'speaker')+'</div>','voice');return;}
   if(action==='record'){closeSheet();$('#btnMic').click();return;}
   if(action==='native')return await openControls('root');if(action==='models')return await openControls('models');if(action.startsWith('control:'))return await openControls(action.slice(8));
   if(action==='voice'){await $('#btnVoice').onclick();return settings();}
   if(action==='language'){uiLanguage=fa()?'en':'fa';applyLanguage();return settings();}
   if(action==='usage')return $('#btnUsage').click();if(action==='manage')return $('#btnSessions').click();if(action==='export')return exportChat();
   if(action==='delete'){deleteTarget=S.data.codex?.current;if(deleteTarget)return confirmDelete();return;}
   if(action==='suggest'){$('#input').value=b.dataset.prompt;autosize();$('#input').focus();return;}
   const [kind,n]=action.split(':');const m=S.msgs.codex?.[Number(n)];if(!m)return;
   if(kind==='copy'){await navigator.clipboard.writeText(m.text);toast(tr('copy'));}
   if(kind==='read')await speak(m);
   if(kind==='share'){if(navigator.share)await navigator.share({text:m.text});else{await navigator.clipboard.writeText(m.text);toast(tr('copy'));}}
  }catch(err){if(err.name!=='AbortError')toast(tr('failed'));}finally{actionBusy=false;}
 });
 drawer.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();closeDrawer();}if(e.key==='Tab'){const items=[...drawer.querySelectorAll('aside button,aside input')].filter(x=>x.getClientRects().length);const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
 const wave=document.createElement('button');wave.id='cxVoice';wave.type='button';wave.className='icon round';wave.dataset.cx='voice-screen';wave.setAttribute('aria-label','گفتگوی صوتی');wave.innerHTML=icon('wave');$('#row').append(wave);
 const quick=document.createElement('div');quick.id='cxComposerControls';quick.innerHTML='<button type="button" data-cx="models" id="cxComposerModel"></button><button type="button" data-cx="control:set:effort" id="cxComposerSpeed"></button>';$('#row').append(quick);
 function syncComposerControls(){
  const d=S.data.codex||{},p=d.preferences||{};
  const model=(p.models||d.models||[]).find(m=>m.id===d.model)?.label||d.model||label('پیش‌فرض','Default');
  const effort=p.effort||'default',names={low:['سریع','Fast'],medium:['متعادل','Balanced'],high:['دقیق','High'],xhigh:['دقیق‌تر','Extra high'],max:['حداکثر','Max'],ultra:['عمیق‌ترین','Ultra']};
  const speed=names[effort]?label(...names[effort]):label('سرعت','Speed');
  $('#cxComposerModel').textContent=model+' ⌄';$('#cxComposerModel').setAttribute('aria-label',label('انتخاب مدل؛ فعلی: ','Choose model; current: ')+model);
  $('#cxComposerSpeed').textContent=speed+' ⌄';$('#cxComposerSpeed').setAttribute('aria-label',label('سرعت و میزان فکرکردن؛ فعلی: ','Speed and reasoning; current: ')+speed);
 }
 const originalAttach=$('#btnAttach').innerHTML,originalSend=$('#btnSend').innerHTML;
 const navWithTheme=setNav;setNav=function(){navWithTheme();syncComposerControls();$('#btnAttach').innerHTML=active()?icon('plus'):originalAttach;$('#btnSend').innerHTML=active()?icon('arrow'):originalSend;if(!active()){$('#app').inert=false;}};
 render.key=null;render();setNav();
})();
