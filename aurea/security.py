from __future__ import annotations
import base64, hashlib, hmac, re, secrets
EMAIL_RE=re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
def b64e(v:bytes)->str:return base64.urlsafe_b64encode(v).decode('ascii')
def b64d(v:str)->bytes:return base64.urlsafe_b64decode(v.encode('ascii'))
def password_hash(password:str)->str:
    salt=secrets.token_bytes(16);iterations=350_000;digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations)
    return f"pbkdf2_sha256${iterations}${b64e(salt)}${b64e(digest)}"
def password_matches(stored:str,password:str)->bool:
    try:
        algo,it,salt,digest=stored.split('$',3)
        if algo!='pbkdf2_sha256':return False
        candidate=hashlib.pbkdf2_hmac('sha256',password.encode(),b64d(salt),int(it))
        return hmac.compare_digest(candidate,b64d(digest))
    except Exception:return False
def password_errors(password:str)->list[str]:
    e=[]
    if len(password)<10:e.append('A senha precisa ter pelo menos 10 caracteres.')
    if not re.search(r'[A-Z]',password):e.append('Inclua pelo menos uma letra maiúscula.')
    if not re.search(r'[a-z]',password):e.append('Inclua pelo menos uma letra minúscula.')
    if not re.search(r'\d',password):e.append('Inclua pelo menos um número.')
    return e
def code_hash(secret:str,code:str)->str:return hmac.new(secret.encode(),code.encode(),hashlib.sha256).hexdigest()
def safety_identifier(secret:str,user_id:int)->str:
    raw=hmac.new(secret.encode(),f'aurea-user:{user_id}'.encode(),hashlib.sha256).hexdigest();return 'aurea_'+raw[:32]
def new_csrf()->str:return secrets.token_urlsafe(32)
