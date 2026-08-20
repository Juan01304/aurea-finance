const demoBtn=document.getElementById('demoBtn');
const status=document.getElementById('demoStatus');
const themeBtn=document.getElementById('themeBtn');
function setTheme(v){document.documentElement.dataset.theme=v;localStorage.setItem('aurea-theme',v)}
setTheme(localStorage.getItem('aurea-theme')||'dark');
themeBtn?.addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
demoBtn?.addEventListener('click',async()=>{
  demoBtn.disabled=true;demoBtn.textContent='Preparando…';status.textContent='Criando um ambiente temporário.';
  try{const r=await fetch('/demo/start',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const d=await r.json();if(!r.ok)throw new Error(d.message||d.error);location.href=d.redirect||'/app'}
  catch(e){demoBtn.disabled=false;demoBtn.textContent='Tentar novamente';status.textContent='Não consegui abrir a demonstração agora.'}
});
if('serviceWorker'in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
