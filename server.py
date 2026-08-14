from __future__ import annotations

import json
import mimetypes
import os
import secrets
import time
from datetime import date
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from aurea.ai import local_assistant
from aurea.db import connect, init_db
from aurea.finance import build_insights, calculate_snapshot, month_key
from aurea.security import new_csrf, password_hash

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
HOST = os.environ.get("AUREA_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", os.environ.get("AUREA_PORT", "10000")))
SECRET = os.environ.get("AUREA_SECRET", secrets.token_hex(32))
SECURE_COOKIE = os.environ.get("AUREA_SECURE_COOKIE", "0") == "1"
SESSION_TTL = 8 * 3600
DEMO_TTL = 24 * 3600


def now():
    return int(time.time())


def get_session(sid):
    c = connect()
    row = c.execute("SELECT * FROM sessions WHERE id=? AND expires_at>?", (sid, now())).fetchone() if sid else None
    if row:
        c.execute("UPDATE sessions SET expires_at=? WHERE id=?", (now() + SESSION_TTL, sid))
        c.commit(); c.close()
        return sid, row, False
    if sid:
        c.execute("DELETE FROM sessions WHERE id=?", (sid,)); c.commit()
    sid = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions(id,csrf,expires_at) VALUES(?,?,?)", (sid, new_csrf(), now() + SESSION_TTL))
    c.commit(); c.close()
    c = connect(); row = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone(); c.close()
    return sid, row, True


def session_user(sid):
    c = connect(); row = c.execute("SELECT user_id FROM sessions WHERE id=?", (sid,)).fetchone(); c.close()
    return int(row["user_id"]) if row and row["user_id"] else None


def set_session_user(sid, uid):
    c = connect(); c.execute("UPDATE sessions SET user_id=?,csrf=?,expires_at=? WHERE id=?", (uid, new_csrf(), now()+SESSION_TTL, sid)); c.commit(); c.close()


def csrf_for(sid):
    c = connect(); row = c.execute("SELECT csrf FROM sessions WHERE id=?", (sid,)).fetchone(); c.close()
    return row["csrf"] if row else ""


def create_demo_user():
    token = secrets.token_hex(8)
    email = f"demo-{token}@aurea.local"
    c = connect()
    cur = c.execute(
        "INSERT INTO users(full_name,email,password_hash,email_verified,is_demo,demo_expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
        ("Visitante Demo", email, password_hash(secrets.token_urlsafe(24)), 1, 1, now()+DEMO_TTL, now()),
    )
    uid = cur.lastrowid
    c.execute("INSERT INTO finance_profiles(user_id,monthly_income,payday,investment_pct,emergency_target,locale,cloud_ai,onboarding_complete) VALUES(?,?,?,?,?,?,?,?)", (uid,2000,5,10,6000,"pt-BR",0,1))
    for name,cat,amount,due,kind in [
        ("Aluguel","Moradia",1000,5,"fixed"),
        ("Água e saneamento","Casa",100,12,"fixed"),
        ("Cartão de crédito","Cartão",750,18,"card"),
    ]:
        c.execute("INSERT INTO bills(user_id,name,category,amount,due_day,kind,recurring,created_at) VALUES(?,?,?,?,?,?,1,?)", (uid,name,cat,amount,due,kind,now()))
    for cat,lim in [("Alimentação",350),("Lazer",150),("Transporte",180)]:
        c.execute("INSERT INTO category_budgets(user_id,category,monthly_limit) VALUES(?,?,?)", (uid,cat,lim))
    c.execute("INSERT INTO goals(user_id,name,target_amount,current_amount,target_date,created_at) VALUES(?,?,?,?,?,?)", (uid,"Reserva de emergência",6000,350,None,now()))
    c.commit(); c.close()
    return uid


def snapshot(uid, month=None):
    month = month_key(month)
    c = connect()
    p = c.execute("SELECT * FROM finance_profiles WHERE user_id=?", (uid,)).fetchone()
    bills = c.execute("SELECT * FROM bills WHERE user_id=? ORDER BY due_day,id", (uid,)).fetchall()
    tx = c.execute("SELECT * FROM transactions WHERE user_id=? AND substr(tx_date,1,7)=? ORDER BY tx_date DESC,id DESC", (uid,month)).fetchall()
    goals = c.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    budgets = c.execute("SELECT * FROM category_budgets WHERE user_id=? ORDER BY category", (uid,)).fetchall()
    statuses = c.execute("SELECT bill_id,paid FROM bill_status WHERE user_id=? AND month=?", (uid,month)).fetchall()
    c.close()
    prof = dict(p) if p else {"monthly_income":0,"investment_pct":10}
    snap = calculate_snapshot(prof,[dict(x) for x in bills],[dict(x) for x in tx],[dict(x) for x in goals],[dict(x) for x in budgets],{int(x["bill_id"]):bool(x["paid"]) for x in statuses},month)
    snap["insights"] = build_insights(snap)
    return snap


def cleanup_demos():
    try:
        c = connect(); rows = c.execute("SELECT id FROM users WHERE is_demo=1 AND demo_expires_at<?", (now(),)).fetchall()
        for r in rows: c.execute("DELETE FROM users WHERE id=?", (r["id"],))
        c.commit(); c.close()
    except Exception as exc:
        print("[cleanup]", exc)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[AUREA]", fmt % args)

    def prepare(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        incoming = jar["aurea_sid"].value if "aurea_sid" in jar else None
        self.sid, self.session, self.new_cookie = get_session(incoming)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Cache-Control", "no-store")
        if getattr(self,"new_cookie",False):
            secure = "; Secure" if SECURE_COOKIE else ""
            self.send_header("Set-Cookie", f"aurea_sid={self.sid}; Path=/; HttpOnly; SameSite=Lax{secure}")
        super().end_headers()

    def json_body(self):
        try:
            n = int(self.headers.get("Content-Length","0")); return json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception: return None

    def send_json(self, obj, status=200):
        raw = json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def send_file(self, path):
        p = PUBLIC_DIR / path
        if not p.exists() or not p.is_file(): return self.send_json({"error":"not_found"},404)
        raw = p.read_bytes(); mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",mime + ("; charset=utf-8" if mime.startswith("text/") or mime in {"application/javascript","application/json"} else "")); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        self.prepare(); path = urlparse(self.path).path
        if path == "/healthz": return self.send_json({"ok":True,"service":"aurea"})
        if path == "/robots.txt":
            raw=b"User-agent: *\nDisallow: /\n"; self.send_response(200); self.send_header("Content-Type","text/plain"); self.send_header("Content-Length",str(len(raw))); self.end_headers(); return self.wfile.write(raw)
        if path in {"/","/index.html"}: return self.send_file("index.html")
        if path == "/app":
            if not session_user(self.sid):
                self.send_response(302); self.send_header("Location","/"); self.end_headers(); return
            return self.send_file("app.html")
        if path.startswith("/static/"): return self.send_file(path[len("/static/"):])
        if path == "/api/me":
            uid = session_user(self.sid)
            if not uid: return self.send_json({"authenticated":False,"csrf":csrf_for(self.sid)})
            c=connect();u=c.execute("SELECT full_name,email,is_demo FROM users WHERE id=?",(uid,)).fetchone();c.close()
            return self.send_json({"authenticated":True,"user":dict(u),"csrf":csrf_for(self.sid)})
        if path == "/api/snapshot":
            uid=session_user(self.sid)
            if not uid:return self.send_json({"error":"unauthorized"},401)
            q=urlparse(self.path).query; month=None
            if q.startswith("month="): month=q.split("=",1)[1]
            return self.send_json(snapshot(uid,month))
        return self.send_json({"error":"not_found"},404)

    def do_POST(self):
        self.prepare(); path=urlparse(self.path).path; body=self.json_body()
        if body is None:return self.send_json({"error":"invalid_json"},400)
        if path == "/demo/start":
            cleanup_demos(); uid=create_demo_user(); set_session_user(self.sid,uid); return self.send_json({"ok":True,"redirect":"/app"})
        uid=session_user(self.sid)
        if not uid:return self.send_json({"error":"unauthorized"},401)
        if self.headers.get("X-CSRF-Token","") != csrf_for(self.sid):return self.send_json({"error":"csrf"},403)
        if path == "/api/bills/add":
            name=str(body.get("name","")).strip()[:80]; amount=max(0,float(body.get("amount") or 0)); due=max(1,min(31,int(body.get("due_day") or 10))); cat=str(body.get("category","Outros"))[:50]; kind=str(body.get("kind","fixed"))[:20]
            if not name or amount<=0:return self.send_json({"error":"invalid_bill"},400)
            c=connect();c.execute("INSERT INTO bills(user_id,name,category,amount,due_day,kind,recurring,created_at) VALUES(?,?,?,?,?,?,1,?)",(uid,name,cat,amount,due,kind,now()));c.commit();c.close();return self.send_json({"ok":True})
        if path == "/api/transactions/add":
            desc=str(body.get("description","")).strip()[:100]; amount=max(0,float(body.get("amount") or 0)); cat=str(body.get("category","Outros"))[:50]; typ="income" if body.get("tx_type")=="income" else "expense"; dt=str(body.get("tx_date") or date.today().isoformat())[:10]
            if not desc or amount<=0:return self.send_json({"error":"invalid_transaction"},400)
            c=connect();c.execute("INSERT INTO transactions(user_id,description,category,amount,tx_type,tx_date,created_at) VALUES(?,?,?,?,?,?,?)",(uid,desc,cat,amount,typ,dt,now()));c.commit();c.close();return self.send_json({"ok":True})
        if path == "/api/bills/toggle-paid":
            bid=int(body.get("id") or 0); mon=month_key(body.get("month"));c=connect();r=c.execute("SELECT paid FROM bill_status WHERE user_id=? AND bill_id=? AND month=?",(uid,bid,mon)).fetchone();paid=0 if r and r["paid"] else 1;c.execute("INSERT INTO bill_status(user_id,bill_id,month,paid,paid_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,bill_id,month) DO UPDATE SET paid=excluded.paid,paid_at=excluded.paid_at",(uid,bid,mon,paid,now() if paid else None));c.commit();c.close();return self.send_json({"ok":True,"paid":bool(paid)})
        if path == "/api/goals/contribute":
            gid=int(body.get("id") or 0); amount=max(0,float(body.get("amount") or 0));c=connect();g=c.execute("SELECT * FROM goals WHERE id=? AND user_id=?",(gid,uid)).fetchone()
            if not g:c.close();return self.send_json({"error":"not_found"},404)
            new=min(float(g["target_amount"]),float(g["current_amount"])+amount);c.execute("UPDATE goals SET current_amount=? WHERE id=?",(new,gid));c.commit();c.close();return self.send_json({"ok":True})
        if path == "/api/assistant":
            msg=str(body.get("message","")).strip()[:1000]
            if not msg:return self.send_json({"error":"empty"},400)
            snap=snapshot(uid,month_key(body.get("month")));ans=local_assistant(msg,snap,"pt-BR");return self.send_json({"ok":True,"answer":ans,"mode":"local"})
        if path == "/api/logout":
            set_session_user(self.sid,None);return self.send_json({"ok":True})
        return self.send_json({"error":"not_found"},404)


def run():
    init_db(); cleanup_demos(); print(f"Aurea Finance em http://{HOST}:{PORT}"); ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__ == "__main__": run()
