const form=document.getElementById('authForm'),title=document.getElementById('authTitle'),sub=document.getElementById('authSubtitle'),msg=document.getElementById('authMessage'),links=document.getElementById('authLinks');
const path=location.pathname,qs=new URLSearchParams(location.search);
function field(label,name,type='text',extra=''){return `<div class="field full"><label>${label}</label><input name="${name}" type="${type}" ${extra} required></div>`}
function button(text){return `<button class="primary full" type="submit">${text}</button>`}
function show(text,tone=''){msg.textContent=text||'';msg.className=`form-message ${tone}`}
async function post(url,data){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json().catch(()=>({}));if(!r.ok)throw Object.assign(new Error(d.message||'Não foi possível concluir.'),{data:d});return d}
function redirect(d){if(d.next)location.href=d.next}
function deliveryNote(d){if(d.delivery==='console')show('Modo local: o código foi exibido no terminal do servidor.','info')}

if(path==='/register'){
  title.textContent='Criar sua conta';sub.textContent='Seu e-mail será confirmado com um código de 6 dígitos.';
  form.innerHTML=field('Nome','full_name')+field('E-mail','email','email','autocomplete="email"')+field('Senha','password','password','minlength="10" autocomplete="new-password"')+`<p class="password-hint">Use 10+ caracteres, maiúscula, minúscula e número.</p>`+button('Criar conta');
  links.innerHTML='Já tem conta? <a href="/login">Entrar</a>';
  form.onsubmit=async e=>{e.preventDefault();show('');const b=Object.fromEntries(new FormData(form));try{const d=await post('/api/auth/register',b);deliveryNote(d);redirect(d)}catch(err){show(err.message,'error')}};
}else if(path==='/verify'){
  const purpose=qs.get('purpose')||'login';
  title.textContent=purpose==='reset'?'Confirmar recuperação':purpose==='verify'?'Confirmar e-mail':'Segundo fator';
  sub.textContent='Digite o código de 6 dígitos enviado para seu e-mail.';
  form.innerHTML=field('Código','code','text','inputmode="numeric" maxlength="6" pattern="[0-9]{6}" autocomplete="one-time-code"')+button('Confirmar código');
  links.innerHTML='<button id="resendBtn" class="link-button" type="button">Reenviar código</button>';
  form.onsubmit=async e=>{e.preventDefault();show('');try{const d=await post('/api/auth/verify',{purpose,code:new FormData(form).get('code')});redirect(d)}catch(err){show(err.message,'error')}};
  document.getElementById('resendBtn').onclick=async()=>{show('');try{const d=await post('/api/auth/resend',{purpose});deliveryNote(d);if(d.delivery!=='console')show('Novo código enviado.','success')}catch(err){show(err.message,'error')}};
}else if(path==='/forgot'){
  title.textContent='Recuperar senha';sub.textContent='Se a conta existir, enviaremos um código para confirmar a troca.';
  form.innerHTML=field('E-mail','email','email','autocomplete="email"')+button('Enviar código');
  links.innerHTML='<a href="/login">Voltar ao login</a>';
  form.onsubmit=async e=>{e.preventDefault();show('');try{const d=await post('/api/auth/forgot',Object.fromEntries(new FormData(form)));deliveryNote(d);redirect(d)}catch(err){show(err.message,'error')}};
}else if(path==='/reset'){
  title.textContent='Criar nova senha';sub.textContent='O código de recuperação precisa ter sido validado nesta sessão.';
  form.innerHTML=field('Nova senha','password','password','minlength="10" autocomplete="new-password"')+`<p class="password-hint">Use 10+ caracteres, maiúscula, minúscula e número.</p>`+button('Atualizar senha');
  links.innerHTML='<a href="/login">Voltar ao login</a>';
  form.onsubmit=async e=>{e.preventDefault();show('');try{const d=await post('/api/auth/reset',Object.fromEntries(new FormData(form)));show(d.message||'Senha atualizada.','success');setTimeout(()=>redirect(d),500)}catch(err){show(err.message,'error')}};
}else{
  title.textContent='Entrar na Aurea';sub.textContent='Primeiro validamos sua senha; depois enviamos um código de acesso.';
  form.innerHTML=field('E-mail','email','email','autocomplete="email"')+field('Senha','password','password','autocomplete="current-password"')+button('Continuar');
  links.innerHTML='<a href="/forgot">Esqueci minha senha</a><span>•</span><a href="/register">Criar conta</a>';
  form.onsubmit=async e=>{e.preventDefault();show('');try{const d=await post('/api/auth/login',Object.fromEntries(new FormData(form)));deliveryNote(d);redirect(d)}catch(err){if(err.data?.next)location.href=err.data.next;else show(err.message,'error')}};
}
