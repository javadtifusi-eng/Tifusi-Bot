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
 const notes=fa?['گفتگو و ایده‌پردازی','کدنویسی و اجرا','مدیریت سرورها','مدیریت سرویس‌ها']:['Think and explore','Build and run','Your servers','Service dashboard'];
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
