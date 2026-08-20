from __future__ import annotations

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("AUREA_DB_PATH", str(BASE_DIR / "aurea.db")))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


class CursorAdapter:
    def __init__(self, cursor, conn, postgres: bool):
        self._cursor = cursor
        self._conn = conn
        self._postgres = postgres

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        if not self._postgres:
            return self._cursor.lastrowid
        row = self._conn._raw.execute("SELECT LASTVAL() AS id").fetchone()
        return int(row["id"] if isinstance(row, dict) else row[0])


class ConnectionAdapter:
    def __init__(self, raw, postgres: bool):
        self._raw = raw
        self._postgres = postgres

    def execute(self, sql: str, params=()):
        if self._postgres:
            sql = sql.replace("?", "%s")
        cur = self._raw.execute(sql, params)
        return CursorAdapter(cur, self, self._postgres)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def using_postgres() -> bool:
    return bool(DATABASE_URL)


def connect() -> ConnectionAdapter:
    if DATABASE_URL:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL foi configurada, mas psycopg não está instalado. Execute: pip install -r requirements.txt"
            ) from exc
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
        return ConnectionAdapter(raw, True)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(DB_PATH, timeout=10)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys=ON")
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA busy_timeout=5000")
    return ConnectionAdapter(raw, False)


def _sqlite_cols(c, table):
    rows = c.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _postgres_cols(c, table):
    rows = c.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
        (table,),
    ).fetchall()
    return {r["column_name"] for r in rows}


def _schema_statements(postgres: bool):
    id_type = "BIGSERIAL PRIMARY KEY" if postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    user_ref = "BIGINT" if postgres else "INTEGER"
    return [
        f"""CREATE TABLE IF NOT EXISTS users(
            id {id_type}, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, email_verified INTEGER NOT NULL DEFAULT 0,
            is_demo INTEGER NOT NULL DEFAULT 0, demo_expires_at BIGINT,
            created_at BIGINT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS sessions(
            id TEXT PRIMARY KEY, user_id {user_ref}, pending_verify {user_ref},
            pending_login {user_ref}, pending_reset {user_ref}, reset_ok INTEGER NOT NULL DEFAULT 0,
            csrf TEXT NOT NULL, expires_at BIGINT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""",
        f"""CREATE TABLE IF NOT EXISTS email_codes(
            id {id_type}, user_id {user_ref} NOT NULL, purpose TEXT NOT NULL,
            code_hash TEXT NOT NULL, expires_at BIGINT NOT NULL, sent_at BIGINT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, consumed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_email_codes_lookup ON email_codes(user_id,purpose,consumed,sent_at)",
        f"""CREATE TABLE IF NOT EXISTS finance_profiles(
            user_id {user_ref} PRIMARY KEY, monthly_income REAL NOT NULL DEFAULT 0,
            payday INTEGER NOT NULL DEFAULT 5, investment_pct REAL NOT NULL DEFAULT 10,
            emergency_target REAL NOT NULL DEFAULT 0, locale TEXT NOT NULL DEFAULT 'pt-BR',
            cloud_ai INTEGER NOT NULL DEFAULT 1, onboarding_complete INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""",
        f"""CREATE TABLE IF NOT EXISTS bills(
            id {id_type}, user_id {user_ref} NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
            amount REAL NOT NULL, due_day INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'fixed',
            recurring INTEGER NOT NULL DEFAULT 1, created_at BIGINT NOT NULL, archived_at BIGINT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""",
        f"""CREATE TABLE IF NOT EXISTS bill_status(
            user_id {user_ref} NOT NULL, bill_id {user_ref} NOT NULL, month TEXT NOT NULL,
            paid INTEGER NOT NULL DEFAULT 0, paid_at BIGINT,
            PRIMARY KEY(user_id,bill_id,month),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(bill_id) REFERENCES bills(id) ON DELETE CASCADE
        )""",
        f"""CREATE TABLE IF NOT EXISTS transactions(
            id {id_type}, user_id {user_ref} NOT NULL, description TEXT NOT NULL,
            category TEXT NOT NULL, amount REAL NOT NULL, tx_type TEXT NOT NULL,
            tx_date TEXT NOT NULL, created_at BIGINT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_transactions_month ON transactions(user_id,tx_date)",
        f"""CREATE TABLE IF NOT EXISTS goals(
            id {id_type}, user_id {user_ref} NOT NULL, name TEXT NOT NULL,
            target_amount REAL NOT NULL, current_amount REAL NOT NULL DEFAULT 0,
            target_date TEXT, created_at BIGINT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""",
        f"""CREATE TABLE IF NOT EXISTS category_budgets(
            id {id_type}, user_id {user_ref} NOT NULL, category TEXT NOT NULL,
            monthly_limit REAL NOT NULL, UNIQUE(user_id,category),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )""",
    ]


def init_db():
    c = connect()
    postgres = using_postgres()
    for statement in _schema_statements(postgres):
        c.execute(statement)

    users_cols = _postgres_cols(c, "users") if postgres else _sqlite_cols(c, "users")
    if "is_demo" not in users_cols:
        c.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
    if "demo_expires_at" not in users_cols:
        c.execute("ALTER TABLE users ADD COLUMN demo_expires_at BIGINT")

    fp_cols = _postgres_cols(c, "finance_profiles") if postgres else _sqlite_cols(c, "finance_profiles")
    if "onboarding_complete" not in fp_cols:
        c.execute("ALTER TABLE finance_profiles ADD COLUMN onboarding_complete INTEGER NOT NULL DEFAULT 0")
    if "cloud_ai" not in fp_cols:
        c.execute("ALTER TABLE finance_profiles ADD COLUMN cloud_ai INTEGER NOT NULL DEFAULT 1")

    bill_cols = _postgres_cols(c, "bills") if postgres else _sqlite_cols(c, "bills")
    if "archived_at" not in bill_cols:
        c.execute("ALTER TABLE bills ADD COLUMN archived_at BIGINT")

    c.commit()
    c.close()
