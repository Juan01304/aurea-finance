from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import secrets
import threading
import time
from datetime import date, datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from aurea.ai import local_assistant, openai_assistant
from aurea.db import connect, init_db
from aurea.emailer import send_otp
from aurea.finance import build_insights, calculate_snapshot, month_key, shift_month
from aurea.security import (
    EMAIL_RE,
    code_hash,
    new_csrf,
    password_errors,
    password_hash,
    password_matches,
)

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
HOST = os.environ.get("AUREA_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", os.environ.get("AUREA_PORT", "10000")))
SECRET = os.environ.get("AUREA_SECRET", secrets.token_hex(32))
SECURE_COOKIE = os.environ.get("AUREA_SECURE_COOKIE", "0") == "1"
ENV = os.environ.get("AUREA_ENV", "development").lower()
SESSION_TTL = 8 * 3600
DEMO_TTL = 24 * 3600
OTP_TTL = 10 * 60
OTP_MAX_ATTEMPTS = 5

_RATE_LOCK = threading.Lock()
_RATE: dict[str, list[int]] = {}


def now() -> int:
    return int(time.time())


def rate_allowed(key: str, limit: int, window: int) -> bool:
    t = now()
    with _RATE_LOCK:
        hits = [x for x in _RATE.get(key, []) if x > t - window]
        if len(hits) >= limit:
            _RATE[key] = hits
            return False
        hits.append(t)
        _RATE[key] = hits
        return True


def get_session(sid):
    c = connect()
    row = c.execute("SELECT * FROM sessions WHERE id=? AND expires_at>?", (sid, now())).fetchone() if sid else None
    if row:
        c.execute("UPDATE sessions SET expires_at=? WHERE id=?", (now() + SESSION_TTL, sid))
        c.commit()
        c.close()
        return sid, row, False
    if sid:
        c.execute("DELETE FROM sessions WHERE id=?", (sid,))
        c.commit()
    sid = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions(id,csrf,expires_at) VALUES(?,?,?)", (sid, new_csrf(), now() + SESSION_TTL))
    c.commit()
    c.close()
    c = connect()
    row = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    c.close()
    return sid, row, True


def session_row(sid):
    c = connect()
    row = c.execute("SELECT * FROM sessions WHERE id=? AND expires_at>?", (sid, now())).fetchone()
    c.close()
    return row


def session_user(sid):
    row = session_row(sid)
    return int(row["user_id"]) if row and row["user_id"] else None


def csrf_for(sid):
    row = session_row(sid)
    return row["csrf"] if row else ""


def set_pending(sid: str, field: str, uid, reset_ok: int | None = None):
    if field not in {"pending_verify", "pending_login", "pending_reset"}:
        raise ValueError("invalid pending field")
    c = connect()
    if reset_ok is None:
        c.execute(f"UPDATE sessions SET {field}=?,csrf=?,expires_at=? WHERE id=?", (uid, new_csrf(), now() + SESSION_TTL, sid))
    else:
        c.execute(
            f"UPDATE sessions SET {field}=?,reset_ok=?,csrf=?,expires_at=? WHERE id=?",
            (uid, reset_ok, new_csrf(), now() + SESSION_TTL, sid),
        )
    c.commit()
    c.close()


def rotate_session(old_sid: str, uid=None) -> str:
    new_sid = secrets.token_urlsafe(32)
    c = connect()
    c.execute("DELETE FROM sessions WHERE id=?", (old_sid,))
    c.execute(
        "INSERT INTO sessions(id,user_id,csrf,expires_at) VALUES(?,?,?,?)",
        (new_sid, uid, new_csrf(), now() + SESSION_TTL),
    )
    c.commit()
    c.close()
    return new_sid


def user_by_email(email: str):
    c = connect()
    row = c.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
    c.close()
    return row


def issue_code(uid: int, purpose: str) -> str:
    code = (
        os.environ.get("AUREA_TEST_OTP", "123456")
        if ENV == "test"
        else f"{secrets.randbelow(1_000_000):06d}"
    )
    c = connect()
    user = c.execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        c.close()
        raise RuntimeError("Usuário não encontrado")
    c.execute("UPDATE email_codes SET consumed=1 WHERE user_id=? AND purpose=? AND consumed=0", (uid, purpose))
    c.execute(
        "INSERT INTO email_codes(user_id,purpose,code_hash,expires_at,sent_at,attempts,consumed) VALUES(?,?,?,?,?,0,0)",
        (uid, purpose, code_hash(SECRET, code), now() + OTP_TTL, now()),
    )
    c.commit()
    try:
        delivery = send_otp(user["email"], code, purpose)
    except Exception:
        c.execute("UPDATE email_codes SET consumed=1 WHERE user_id=? AND purpose=? AND consumed=0", (uid, purpose))
        c.commit()
        c.close()
        raise
    c.close()
    return delivery


def verify_code(uid: int, purpose: str, code: str) -> tuple[bool, str]:
    c = connect()
    row = c.execute(
        "SELECT * FROM email_codes WHERE user_id=? AND purpose=? AND consumed=0 ORDER BY sent_at DESC,id DESC LIMIT 1",
        (uid, purpose),
    ).fetchone()
    if not row:
        c.close()
        return False, "Código não encontrado. Peça um novo código."
    if int(row["expires_at"]) < now():
        c.execute("UPDATE email_codes SET consumed=1 WHERE id=?", (row["id"],))
        c.commit()
        c.close()
        return False, "O código expirou. Peça um novo."
    attempts = int(row["attempts"]) + 1
    c.execute("UPDATE email_codes SET attempts=? WHERE id=?", (attempts, row["id"]))
    if attempts > OTP_MAX_ATTEMPTS:
        c.execute("UPDATE email_codes SET consumed=1 WHERE id=?", (row["id"],))
        c.commit()
        c.close()
        return False, "Muitas tentativas. Peça um novo código."
    ok = secrets.compare_digest(row["code_hash"], code_hash(SECRET, str(code).strip()))
    if ok:
        c.execute("UPDATE email_codes SET consumed=1 WHERE id=?", (row["id"],))
    c.commit()
    c.close()
    return ok, "" if ok else "Código incorreto."


def create_demo_user():
    token = secrets.token_hex(8)
    email = f"demo-{token}@aurea.local"
    c = connect()
    cur = c.execute(
        "INSERT INTO users(full_name,email,password_hash,email_verified,is_demo,demo_expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
        ("Visitante Demo", email, password_hash(secrets.token_urlsafe(24)), 1, 1, now() + DEMO_TTL, now()),
    )
    uid = cur.lastrowid
    c.execute(
        "INSERT INTO finance_profiles(user_id,monthly_income,payday,investment_pct,emergency_target,locale,cloud_ai,onboarding_complete) VALUES(?,?,?,?,?,?,?,?)",
        (uid, 2000, 5, 10, 6000, "pt-BR", 0, 1),
    )
    for name, cat, amount, due, kind in [
        ("Aluguel", "Moradia", 1000, 5, "fixed"),
        ("Água e saneamento", "Casa", 100, 12, "fixed"),
        ("Cartão de crédito", "Cartão", 750, 18, "card"),
    ]:
        c.execute(
            "INSERT INTO bills(user_id,name,category,amount,due_day,kind,recurring,created_at) VALUES(?,?,?,?,?,?,1,?)",
            (uid, name, cat, amount, due, kind, now()),
        )
    for cat, lim in [("Alimentação", 350), ("Lazer", 150), ("Transporte", 180)]:
        c.execute("INSERT INTO category_budgets(user_id,category,monthly_limit) VALUES(?,?,?)", (uid, cat, lim))
    c.execute(
        "INSERT INTO goals(user_id,name,target_amount,current_amount,target_date,created_at) VALUES(?,?,?,?,?,?)",
        (uid, "Reserva de emergência", 6000, 350, None, now()),
    )
    c.commit()
    c.close()
    return uid


def month_epoch_bounds(month: str) -> tuple[int, int]:
    y, m = map(int, month.split("-"))
    start = int(datetime(y, m, 1).timestamp())
    if m == 12:
        end = int(datetime(y + 1, 1, 1).timestamp())
    else:
        end = int(datetime(y, m + 1, 1).timestamp())
    return start, end


def snapshot(uid, month=None):
    month = month_key(month)
    start_ts, next_ts = month_epoch_bounds(month)
    c = connect()
    p = c.execute("SELECT * FROM finance_profiles WHERE user_id=?", (uid,)).fetchone()
    all_bills = c.execute("SELECT * FROM bills WHERE user_id=? ORDER BY due_day,id", (uid,)).fetchall()
    bills = [
        x for x in all_bills
        if int(x["created_at"]) < next_ts and (x["archived_at"] is None or int(x["archived_at"]) >= start_ts)
    ]
    tx = c.execute(
        "SELECT * FROM transactions WHERE user_id=? AND substr(tx_date,1,7)=? ORDER BY tx_date DESC,id DESC",
        (uid, month),
    ).fetchall()
    goals = c.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    budgets = c.execute("SELECT * FROM category_budgets WHERE user_id=? ORDER BY category", (uid,)).fetchall()
    statuses = c.execute("SELECT bill_id,paid FROM bill_status WHERE user_id=? AND month=?", (uid, month)).fetchall()
    c.close()
    prof = dict(p) if p else {"monthly_income": 0, "investment_pct": 10, "locale": "pt-BR", "cloud_ai": 0}
    snap = calculate_snapshot(
        prof,
        [dict(x) for x in bills],
        [dict(x) for x in tx],
        [dict(x) for x in goals],
        [dict(x) for x in budgets],
        {int(x["bill_id"]): bool(x["paid"]) for x in statuses},
        month,
    )
    snap["insights"] = build_insights(snap)
    return snap


def history(uid: int, count: int = 6):
    current = month_key()
    rows = []
    for offset in range(-(count - 1), 1):
        mon = shift_month(current, offset)
        s = snapshot(uid, mon)
        m = s["metrics"]
        rows.append({
            "month": mon,
            "income": m["total_income"],
            "committed": m["committed"],
            "spent": m["variable_spent"],
            "safe": m["safe_to_spend"],
            "saved": m["suggested_save"],
            "score": m["health_score"],
        })
    return rows


def cleanup_demos():
    try:
        c = connect()
        rows = c.execute("SELECT id FROM users WHERE is_demo=1 AND demo_expires_at<?", (now(),)).fetchall()
        for r in rows:
            c.execute("DELETE FROM users WHERE id=?", (r["id"],))
        c.execute("DELETE FROM sessions WHERE expires_at<?", (now(),))
        c.commit()
        c.close()
    except Exception as exc:
        print("[cleanup]", exc)


class Handler(BaseHTTPRequestHandler):
    server_version = "AureaHTTP/3.1"

    def log_message(self, fmt, *args):
        print("[AUREA]", fmt % args)

    def client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        return forwarded or self.client_address[0]

    def limited(self, scope: str, limit: int, window: int):
        if rate_allowed(f"{self.client_ip()}:{scope}", limit, window):
            return False
        self.send_json({"error": "rate_limited", "message": "Muitas tentativas. Aguarde um pouco e tente novamente."}, 429)
        return True

    def prepare(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        incoming = jar["aurea_sid"].value if "aurea_sid" in jar else None
        self.sid, self.session, self.new_cookie = get_session(incoming)

    def rotate(self, uid=None):
        self.sid = rotate_session(self.sid, uid)
        self.session = session_row(self.sid)
        self.new_cookie = True

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        path = urlparse(self.path).path
        if path.startswith("/app") or path.startswith("/api/") or path in {"/login", "/register", "/verify", "/forgot", "/reset", "/onboarding"}:
            self.send_header("X-Robots-Tag", "noindex, nofollow")
        if path.startswith("/api/") or path in {"/app", "/onboarding"}:
            self.send_header("Cache-Control", "no-store")
        if getattr(self, "new_cookie", False):
            secure = "; Secure" if SECURE_COOKIE else ""
            self.send_header(
                "Set-Cookie",
                f"aurea_sid={self.sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}{secure}",
            )
        super().end_headers()

    def json_body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 1_000_000:
                return None
            return json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception:
            return None

    def send_bytes(self, raw: bytes, content_type: str, status=200, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(raw)

    def send_json(self, obj, status=200):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_bytes(raw, "application/json; charset=utf-8", status)

    def send_file(self, path):
        p = (PUBLIC_DIR / path).resolve()
        if PUBLIC_DIR.resolve() not in p.parents or not p.exists() or not p.is_file():
            return self.send_json({"error": "not_found"}, 404)
        raw = p.read_bytes()
        mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json", "application/manifest+json"}:
            mime += "; charset=utf-8"
        self.send_bytes(raw, mime)

    def require_user(self):
        uid = session_user(self.sid)
        if not uid:
            self.send_json({"error": "unauthorized"}, 401)
            return None
        return uid

    def require_csrf(self):
        if self.headers.get("X-CSRF-Token", "") != csrf_for(self.sid):
            self.send_json({"error": "csrf"}, 403)
            return False
        return True

    def do_GET(self):
        self.prepare()
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/healthz":
            return self.send_json({"ok": True, "service": "aurea", "version": "3.1"})
        if path == "/robots.txt":
            return self.send_bytes(b"User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /api/\n", "text/plain; charset=utf-8")
        if path in {"/", "/index.html"}:
            return self.send_file("index.html")
        if path in {"/login", "/register", "/verify", "/forgot", "/reset"}:
            return self.send_file("auth.html")
        if path == "/privacidade":
            return self.send_file("privacy.html")
        if path == "/termos":
            return self.send_file("terms.html")
        if path == "/manifest.webmanifest":
            return self.send_file("manifest.webmanifest")
        if path == "/sw.js":
            return self.send_file("sw.js")
        if path == "/icon.svg":
            return self.send_file("icon.svg")
        if path == "/onboarding":
            uid = session_user(self.sid)
            if not uid:
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            return self.send_file("onboarding.html")
        if path == "/app":
            uid = session_user(self.sid)
            if not uid:
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            c = connect()
            profile = c.execute("SELECT onboarding_complete FROM finance_profiles WHERE user_id=?", (uid,)).fetchone()
            c.close()
            if profile and not profile["onboarding_complete"]:
                self.send_response(302)
                self.send_header("Location", "/onboarding")
                self.end_headers()
                return
            return self.send_file("app.html")
        if path.startswith("/static/"):
            return self.send_file(path[len("/static/"):])

        if path == "/api/me":
            uid = session_user(self.sid)
            if not uid:
                return self.send_json({"authenticated": False, "csrf": csrf_for(self.sid)})
            c = connect()
            u = c.execute("SELECT full_name,email,is_demo FROM users WHERE id=?", (uid,)).fetchone()
            p = c.execute("SELECT * FROM finance_profiles WHERE user_id=?", (uid,)).fetchone()
            c.close()
            ai_mode = "cloud" if p and p["cloud_ai"] and os.environ.get("OPENAI_API_KEY", "").strip() and not u["is_demo"] else "local"
            return self.send_json({
                "authenticated": True,
                "user": dict(u),
                "profile": dict(p) if p else None,
                "csrf": csrf_for(self.sid),
                "ai_mode": ai_mode,
            })

        if path == "/api/snapshot":
            uid = self.require_user()
            if not uid:
                return
            return self.send_json(snapshot(uid, qs.get("month", [None])[0]))

        if path == "/api/history":
            uid = self.require_user()
            if not uid:
                return
            return self.send_json({"months": history(uid, 6)})

        if path == "/api/export":
            uid = self.require_user()
            if not uid:
                return
            fmt = qs.get("format", ["json"])[0].lower()
            c = connect()
            user = c.execute("SELECT full_name,email,created_at FROM users WHERE id=?", (uid,)).fetchone()
            profile = c.execute("SELECT * FROM finance_profiles WHERE user_id=?", (uid,)).fetchone()
            bills = c.execute("SELECT * FROM bills WHERE user_id=? ORDER BY id", (uid,)).fetchall()
            tx = c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY tx_date,id", (uid,)).fetchall()
            goals = c.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id", (uid,)).fetchall()
            budgets = c.execute("SELECT * FROM category_budgets WHERE user_id=? ORDER BY category", (uid,)).fetchall()
            statuses = c.execute("SELECT * FROM bill_status WHERE user_id=? ORDER BY month,bill_id", (uid,)).fetchall()
            c.close()
            data = {
                "exported_at": now(),
                "user": dict(user),
                "profile": dict(profile) if profile else {},
                "bills": [dict(x) for x in bills],
                "transactions": [dict(x) for x in tx],
                "goals": [dict(x) for x in goals],
                "budgets": [dict(x) for x in budgets],
                "bill_status": [dict(x) for x in statuses],
            }
            if fmt == "csv":
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["tipo", "data", "descricao", "categoria", "valor", "detalhe"])
                for t in tx:
                    writer.writerow([t["tx_type"], t["tx_date"], t["description"], t["category"], t["amount"], "transacao"])
                for b in bills:
                    writer.writerow(["bill", "", b["name"], b["category"], b["amount"], f"vence dia {b['due_day']}"])
                raw = ("\ufeff" + output.getvalue()).encode("utf-8")
                return self.send_bytes(raw, "text/csv; charset=utf-8", filename="aurea-export.csv")
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode()
            return self.send_bytes(raw, "application/json; charset=utf-8", filename="aurea-export.json")

        return self.send_json({"error": "not_found"}, 404)

    def do_POST(self):
        self.prepare()
        path = urlparse(self.path).path
        body = self.json_body()
        if body is None:
            return self.send_json({"error": "invalid_json"}, 400)

        if path == "/demo/start":
            if self.limited("demo", 15, 3600):
                return
            cleanup_demos()
            uid = create_demo_user()
            self.rotate(uid)
            return self.send_json({"ok": True, "redirect": "/app"})

        if path == "/api/auth/register":
            if self.limited("register", 8, 900):
                return
            name = str(body.get("full_name", "")).strip()[:80]
            email = str(body.get("email", "")).strip().lower()[:200]
            password = str(body.get("password", ""))
            if len(name) < 2 or not EMAIL_RE.fullmatch(email):
                return self.send_json({"error": "invalid_fields", "message": "Confira nome e e-mail."}, 400)
            p_errors = password_errors(password)
            if p_errors:
                return self.send_json({"error": "weak_password", "message": " ".join(p_errors)}, 400)
            c = connect()
            existing = c.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
            if existing and existing["email_verified"]:
                c.close()
                return self.send_json({"error": "email_exists", "message": "Já existe uma conta com este e-mail."}, 409)
            if existing:
                uid = int(existing["id"])
                c.execute("UPDATE users SET full_name=?,password_hash=? WHERE id=?", (name, password_hash(password), uid))
            else:
                cur = c.execute(
                    "INSERT INTO users(full_name,email,password_hash,email_verified,is_demo,created_at) VALUES(?,?,?,?,0,?)",
                    (name, email, password_hash(password), 0, now()),
                )
                uid = cur.lastrowid
                c.execute(
                    "INSERT INTO finance_profiles(user_id,monthly_income,payday,investment_pct,emergency_target,locale,cloud_ai,onboarding_complete) VALUES(?,?,?,?,?,?,?,0)",
                    (uid, 0, 5, 10, 0, "pt-BR", 1),
                )
            c.commit()
            c.close()
            try:
                delivery = issue_code(uid, "verify")
            except Exception as exc:
                if not existing:
                    c = connect()
                    c.execute("DELETE FROM users WHERE id=?", (uid,))
                    c.commit()
                    c.close()
                print("[email]", exc)
                return self.send_json({"error": "email_unavailable", "message": "Não foi possível enviar o código agora."}, 503)
            set_pending(self.sid, "pending_verify", uid)
            return self.send_json({"ok": True, "delivery": delivery, "next": "/verify?purpose=verify"})

        if path == "/api/auth/login":
            if self.limited("login", 12, 900):
                return
            email = str(body.get("email", "")).strip().lower()[:200]
            password = str(body.get("password", ""))
            user = user_by_email(email)
            if not user or not password_matches(user["password_hash"], password):
                return self.send_json({"error": "invalid_credentials", "message": "E-mail ou senha inválidos."}, 401)
            if not user["email_verified"]:
                set_pending(self.sid, "pending_verify", int(user["id"]))
                try:
                    delivery = issue_code(int(user["id"]), "verify")
                except Exception as exc:
                    print("[email]", exc)
                    return self.send_json({"error": "email_unavailable", "message": "Não foi possível enviar o código agora."}, 503)
                return self.send_json({"error": "email_not_verified", "delivery": delivery, "next": "/verify?purpose=verify"}, 403)
            try:
                delivery = issue_code(int(user["id"]), "login")
            except Exception as exc:
                print("[email]", exc)
                return self.send_json({"error": "email_unavailable", "message": "Não foi possível enviar o código agora."}, 503)
            set_pending(self.sid, "pending_login", int(user["id"]))
            return self.send_json({"ok": True, "delivery": delivery, "next": "/verify?purpose=login"})

        if path == "/api/auth/forgot":
            if self.limited("forgot", 8, 900):
                return
            email = str(body.get("email", "")).strip().lower()[:200]
            user = user_by_email(email)
            if user and user["email_verified"]:
                try:
                    delivery = issue_code(int(user["id"]), "reset")
                    set_pending(self.sid, "pending_reset", int(user["id"]), reset_ok=0)
                    return self.send_json({"ok": True, "delivery": delivery, "next": "/verify?purpose=reset"})
                except Exception as exc:
                    print("[email]", exc)
            return self.send_json({"ok": True, "next": "/verify?purpose=reset", "message": "Se o e-mail existir, um código foi enviado."})

        if path == "/api/auth/resend":
            if self.limited("resend", 5, 600):
                return
            purpose = str(body.get("purpose", ""))
            field = {"verify": "pending_verify", "login": "pending_login", "reset": "pending_reset"}.get(purpose)
            row = session_row(self.sid)
            uid = int(row[field]) if row and field and row[field] else None
            if not uid:
                return self.send_json({"error": "no_pending_flow", "message": "Inicie o fluxo novamente."}, 400)
            try:
                delivery = issue_code(uid, purpose)
            except Exception as exc:
                print("[email]", exc)
                return self.send_json({"error": "email_unavailable", "message": "Não foi possível reenviar o código."}, 503)
            return self.send_json({"ok": True, "delivery": delivery})

        if path == "/api/auth/verify":
            if self.limited("verify", 20, 900):
                return
            purpose = str(body.get("purpose", ""))
            code = str(body.get("code", "")).strip()
            field = {"verify": "pending_verify", "login": "pending_login", "reset": "pending_reset"}.get(purpose)
            row = session_row(self.sid)
            uid = int(row[field]) if row and field and row[field] else None
            if not uid:
                return self.send_json({"error": "no_pending_flow", "message": "Inicie o fluxo novamente."}, 400)
            ok, message = verify_code(uid, purpose, code)
            if not ok:
                return self.send_json({"error": "invalid_code", "message": message}, 400)
            if purpose == "reset":
                set_pending(self.sid, "pending_reset", uid, reset_ok=1)
                return self.send_json({"ok": True, "next": "/reset"})
            if purpose == "verify":
                c = connect()
                c.execute("UPDATE users SET email_verified=1 WHERE id=?", (uid,))
                c.commit()
                c.close()
            self.rotate(uid)
            c = connect()
            p = c.execute("SELECT onboarding_complete FROM finance_profiles WHERE user_id=?", (uid,)).fetchone()
            c.close()
            return self.send_json({"ok": True, "next": "/app" if p and p["onboarding_complete"] else "/onboarding"})

        if path == "/api/auth/reset":
            if self.limited("reset", 8, 900):
                return
            row = session_row(self.sid)
            uid = int(row["pending_reset"]) if row and row["pending_reset"] and row["reset_ok"] else None
            if not uid:
                return self.send_json({"error": "reset_not_verified", "message": "Valide o código antes de trocar a senha."}, 403)
            password = str(body.get("password", ""))
            errors = password_errors(password)
            if errors:
                return self.send_json({"error": "weak_password", "message": " ".join(errors)}, 400)
            c = connect()
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password), uid))
            c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            c.execute("DELETE FROM email_codes WHERE user_id=? AND purpose='reset'", (uid,))
            c.commit()
            c.close()
            self.rotate(None)
            return self.send_json({"ok": True, "next": "/login", "message": "Senha atualizada."})

        uid = self.require_user()
        if not uid:
            return
        if not self.require_csrf():
            return

        if path == "/api/profile":
            try:
                income = max(0.0, float(body.get("monthly_income") or 0))
                payday = max(1, min(31, int(body.get("payday") or 5)))
                invest = max(0.0, min(100.0, float(body.get("investment_pct") or 0)))
                emergency = max(0.0, float(body.get("emergency_target") or 0))
            except (TypeError, ValueError):
                return self.send_json({"error": "invalid_profile"}, 400)
            locale = "en-US" if body.get("locale") == "en-US" else "pt-BR"
            cloud_ai = 1 if body.get("cloud_ai", True) else 0
            c = connect()
            c.execute(
                "UPDATE finance_profiles SET monthly_income=?,payday=?,investment_pct=?,emergency_target=?,locale=?,cloud_ai=?,onboarding_complete=1 WHERE user_id=?",
                (income, payday, invest, emergency, locale, cloud_ai, uid),
            )
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/bills/add":
            try:
                amount = max(0, float(body.get("amount") or 0))
                due = max(1, min(31, int(body.get("due_day") or 10)))
            except (TypeError, ValueError):
                return self.send_json({"error": "invalid_bill"}, 400)
            name = str(body.get("name", "")).strip()[:80]
            cat = str(body.get("category", "Outros")).strip()[:50] or "Outros"
            kind = str(body.get("kind", "fixed"))[:20]
            if kind not in {"fixed", "card", "subscription", "debt"}:
                kind = "fixed"
            if not name or amount <= 0:
                return self.send_json({"error": "invalid_bill"}, 400)
            c = connect()
            c.execute(
                "INSERT INTO bills(user_id,name,category,amount,due_day,kind,recurring,created_at) VALUES(?,?,?,?,?,?,1,?)",
                (uid, name, cat, amount, due, kind, now()),
            )
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/bills/archive":
            bid = int(body.get("id") or 0)
            c = connect()
            c.execute("UPDATE bills SET archived_at=? WHERE id=? AND user_id=?", (now(), bid, uid))
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/transactions/add":
            desc = str(body.get("description", "")).strip()[:100]
            cat = str(body.get("category", "Outros")).strip()[:50] or "Outros"
            typ = "income" if body.get("tx_type") == "income" else "expense"
            dt = str(body.get("tx_date") or date.today().isoformat())[:10]
            try:
                datetime.strptime(dt, "%Y-%m-%d")
                amount = max(0, float(body.get("amount") or 0))
            except (TypeError, ValueError):
                return self.send_json({"error": "invalid_transaction"}, 400)
            if not desc or amount <= 0:
                return self.send_json({"error": "invalid_transaction"}, 400)
            c = connect()
            c.execute(
                "INSERT INTO transactions(user_id,description,category,amount,tx_type,tx_date,created_at) VALUES(?,?,?,?,?,?,?)",
                (uid, desc, cat, amount, typ, dt, now()),
            )
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/transactions/delete":
            tid = int(body.get("id") or 0)
            c = connect()
            c.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tid, uid))
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/bills/toggle-paid":
            bid = int(body.get("id") or 0)
            mon = month_key(body.get("month"))
            c = connect()
            owned = c.execute("SELECT id FROM bills WHERE id=? AND user_id=?", (bid, uid)).fetchone()
            if not owned:
                c.close()
                return self.send_json({"error": "not_found"}, 404)
            r = c.execute("SELECT paid FROM bill_status WHERE user_id=? AND bill_id=? AND month=?", (uid, bid, mon)).fetchone()
            paid = 0 if r and r["paid"] else 1
            c.execute(
                "INSERT INTO bill_status(user_id,bill_id,month,paid,paid_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,bill_id,month) DO UPDATE SET paid=excluded.paid,paid_at=excluded.paid_at",
                (uid, bid, mon, paid, now() if paid else None),
            )
            c.commit()
            c.close()
            return self.send_json({"ok": True, "paid": bool(paid)})

        if path == "/api/goals/add":
            name = str(body.get("name", "")).strip()[:80]
            target_date = str(body.get("target_date") or "").strip()[:10] or None
            try:
                target = max(0, float(body.get("target_amount") or 0))
                current = max(0, float(body.get("current_amount") or 0))
                if target_date:
                    datetime.strptime(target_date, "%Y-%m-%d")
            except (TypeError, ValueError):
                return self.send_json({"error": "invalid_goal"}, 400)
            if not name or target <= 0:
                return self.send_json({"error": "invalid_goal"}, 400)
            current = min(current, target)
            c = connect()
            c.execute(
                "INSERT INTO goals(user_id,name,target_amount,current_amount,target_date,created_at) VALUES(?,?,?,?,?,?)",
                (uid, name, target, current, target_date, now()),
            )
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/goals/contribute":
            gid = int(body.get("id") or 0)
            try:
                amount = max(0, float(body.get("amount") or 0))
            except (TypeError, ValueError):
                return self.send_json({"error": "invalid_amount"}, 400)
            c = connect()
            g = c.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (gid, uid)).fetchone()
            if not g:
                c.close()
                return self.send_json({"error": "not_found"}, 404)
            new = min(float(g["target_amount"]), float(g["current_amount"]) + amount)
            c.execute("UPDATE goals SET current_amount=? WHERE id=?", (new, gid))
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/goals/delete":
            gid = int(body.get("id") or 0)
            c = connect()
            c.execute("DELETE FROM goals WHERE id=? AND user_id=?", (gid, uid))
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/budgets/upsert":
            cat = str(body.get("category", "")).strip()[:50]
            try:
                limit = max(0, float(body.get("monthly_limit") or 0))
            except (TypeError, ValueError):
                return self.send_json({"error": "invalid_budget"}, 400)
            if not cat or limit <= 0:
                return self.send_json({"error": "invalid_budget"}, 400)
            c = connect()
            c.execute(
                "INSERT INTO category_budgets(user_id,category,monthly_limit) VALUES(?,?,?) ON CONFLICT(user_id,category) DO UPDATE SET monthly_limit=excluded.monthly_limit",
                (uid, cat, limit),
            )
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/budgets/delete":
            cat = str(body.get("category", "")).strip()[:50]
            c = connect()
            c.execute("DELETE FROM category_budgets WHERE user_id=? AND category=?", (uid, cat))
            c.commit()
            c.close()
            return self.send_json({"ok": True})

        if path == "/api/assistant":
            if self.limited("assistant", 30, 60):
                return
            msg = str(body.get("message", "")).strip()[:1000]
            if not msg:
                return self.send_json({"error": "empty"}, 400)
            snap = snapshot(uid, month_key(body.get("month")))
            profile = snap.get("profile", {})
            is_demo = False
            c = connect()
            u = c.execute("SELECT is_demo FROM users WHERE id=?", (uid,)).fetchone()
            c.close()
            is_demo = bool(u and u["is_demo"])
            mode = "local"
            if profile.get("cloud_ai") and os.environ.get("OPENAI_API_KEY", "").strip() and not is_demo:
                try:
                    ans = openai_assistant(msg, snap, profile.get("locale", "pt-BR"), uid, SECRET)
                    mode = "cloud"
                except Exception as exc:
                    print("[openai fallback]", exc)
                    ans = local_assistant(msg, snap, profile.get("locale", "pt-BR"))
            else:
                ans = local_assistant(msg, snap, profile.get("locale", "pt-BR"))
            return self.send_json({"ok": True, "answer": ans, "mode": mode})

        if path == "/api/account/delete":
            password = str(body.get("password", ""))
            c = connect()
            user = c.execute("SELECT password_hash,is_demo FROM users WHERE id=?", (uid,)).fetchone()
            if not user or (not user["is_demo"] and not password_matches(user["password_hash"], password)):
                c.close()
                return self.send_json({"error": "invalid_password", "message": "Senha incorreta."}, 403)
            c.execute("DELETE FROM users WHERE id=?", (uid,))
            c.commit()
            c.close()
            self.rotate(None)
            return self.send_json({"ok": True, "next": "/"})

        if path == "/api/logout":
            self.rotate(None)
            return self.send_json({"ok": True})

        return self.send_json({"error": "not_found"}, 404)


def run():
    init_db()
    cleanup_demos()
    print(f"Aurea Finance em http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    run()
