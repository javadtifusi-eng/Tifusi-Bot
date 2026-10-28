'use strict';
// Appearance and navigation only: CLI jobs, sessions and SSH transport stay in their existing modules.
document.body.appendChild($('#workspaceDock'));
const previousWorkspaceNav=setNav;
let workspaceReturnHome=false;
setNav=function(){
 previousWorkspaceNav();
 const active=view==='home'?'home':view==='settings'||view==='ssh-settings'?'settings':S.tab==='ssh'?'ssh':engine;
 document.querySelectorAll('#workspaceDock [data-dock]').forEach(b=>{const on=b.dataset.dock===active;b.classList.toggle('on',on);b.setAttribute('aria-selected',String(on));});
 const fa=uiLanguage==='fa';
 $('#workspaceDock [data-dock=home] .dock-label').textContent=fa?'خانه':'Home';
 $('#workspaceDock [data-dock=settings] .dock-label').textContent=fa?'تنظیمات':'Settings';
 $('.home-kicker').textContent=fa?'فضای کار شخصی':'PERSONAL WORKSPACE';
 $('.home-heading h1').textContent=fa?'همه‌چیز، همین‌جاست.':'Everything, together.';
 $('.home-heading p').textContent=fa?'گفتگو، کدنویسی و مدیریت سرورها':'Conversations, code and your servers';
 const notes=fa?['کدنویسی و اجرا','گفتگو و ایده‌پردازی','مدیریت سرورها','مدیریت سرویس‌ها']:['Build and run','Think and explore','Your servers','Service dashboard'];
 document.querySelectorAll('.workspace-card small').forEach((el,i)=>el.textContent=notes[i]);
 $('#homePanel b').textContent=fa?'پنل تیفوسی':'Tifusi panel';
 $('.home-bottom>span').lastChild.textContent=fa?'خصوصی · فقط شما':'Private · only you';
 $('[data-home-sessions]').textContent=fa?'ادامهٔ گفتگوها ←':'Continue a conversation →';
 document.querySelectorAll('#workspaceDock button').forEach(b=>b.title=b.textContent.trim());
};
const workspaceCloseSheet=closeSheet;
closeSheet=function(){workspaceCloseSheet();if(workspaceReturnHome){workspaceReturnHome=false;view='home';setNav();}};
$('#sheetClose').onclick=()=>closeSheet();$('.sheet-bg').onclick=()=>closeSheet();
document.querySelectorAll('#workspaceDock [data-dock]').forEach(b=>b.onclick=()=>{
 const key=b.dataset.dock;
 if(key==='home'){workspaceReturnHome=false;showAssistantHome();return;}
 if(key==='settings'){
  workspaceReturnHome=view==='home';
  if(S.tab==='ssh')openSshSettings();else openControls('root');
  return;
 }
 workspaceReturnHome=false;
 if(key==='ssh')switchWorkspace(engine,'ssh');else switchWorkspace(key,'chat');
});
$('[data-home-sessions]').onclick=()=>{workspaceReturnHome=false;switchWorkspace(engine,'sessions');};
setNav();

// Decorate each newly rendered sheet without observers or network requests.
const settingPaths={
 model:'M12 3l3 6 6 3-6 3-3 6-3-6-6-3 6-3z',
 thinking:'M9 18h6m-5 3h4M8 15a7 7 0 1 1 8 0v2H8z',
 shield:'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6',
 bell:'M6 17h12l-2-3V9a4 4 0 0 0-8 0v5z M10 21h4',
 language:'M3 5h12M9 3v2M5 5c0 6 6 10 9 11M13 5c0 5-4 9-10 11M14 21l4-10 4 10M16 17h4',
 voice:'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0z M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8',
 sessions:'M5 4h14v16H5z M8 8h8M8 12h8M8 16h5',
 usage:'M4 20V12h3v8M10 20V4h3v16M16 20V8h3v12',
 install:'M5 16v5h14v-5M12 3v12M7 10l5 5 5-5',
 back:'M9 5l-7 7 7 7M2 12h19',
 server:'M3 3h18v7H3z M3 14h18v7H3z M6 6h1M6 17h1',
 tone:'M3 4h18v13H9l-6 4z M7 9h10M7 13h6',
 check:'M4 12l5 5L20 6'
};
function settingIcon(key){return '<span class="setting-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="'+settingPaths[key]+'"/></svg></span>';}
const workspaceSheetWithIcons=sheet;
sheet=function(content){
 workspaceSheetWithIcons(content);
 const heading=$('#sheetContent h3');
 if(heading&&/Claude|Codex/.test(heading.textContent))heading.insertAdjacentHTML('afterbegin','<span class="setting-icon" aria-hidden="true"><img src="s/'+(engine==='claude'?'claude.svg':'openai.svg')+'" alt=""></span>');
 document.querySelectorAll('#sheetContent .control-row button,#sheetContent .workspace-options button,#sheetContent .ssh-settings-row button').forEach(b=>{
  const t=b.textContent.toLowerCase();
  let key=/مدل|model/.test(t)?'model':/فکر|reason|think/.test(t)?'thinking':/تأیید|دسترسی|approval|sandbox|permission/.test(t)?'shield':/اعلان|notif/.test(t)?'bell':/زبان|language/.test(t)?'language':/ویس|voice|صدا/.test(t)?'voice':/جلسه|session/.test(t)?'sessions':/مصرف|usage/.test(t)?'usage':/صفحه.*گوشی|install|home screen/.test(t)?'install':/بازگشت|back/.test(t)?'back':/سرور|server|کلید/.test(t)?'server':/لحن|tone/.test(t)?'tone':'check';
  if(/انتخاب دستیار|choose assistant/.test(t))b.insertAdjacentHTML('afterbegin','<span class="setting-icon" aria-hidden="true"><img src="s/claude.svg" alt=""></span><span class="setting-icon" aria-hidden="true"><img src="s/openai.svg" alt=""></span>');
  else b.insertAdjacentHTML('afterbegin',settingIcon(key));
 });
};
