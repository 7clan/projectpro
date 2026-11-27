"""SQLite persistence and minimal token-based authentication for a prototype."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  password_hash TEXT, created_at TEXT NOT NULL, exam_date TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS challenges (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
  length REAL NOT NULL, load REAL NOT NULL, position REAL NOT NULL, udl REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), challenge_id TEXT NOT NULL REFERENCES challenges(id),
  stage TEXT NOT NULL, concept TEXT NOT NULL, correct INTEGER NOT NULL, misconception TEXT,
  input TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(user_id,challenge_id,stage)
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
  subject TEXT NOT NULL, data BLOB NOT NULL, page_count INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_pages (
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page INTEGER NOT NULL, content TEXT NOT NULL, PRIMARY KEY(document_id,page)
);
CREATE TABLE IF NOT EXISTS reading_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id),
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, page INTEGER NOT NULL,
  activity TEXT NOT NULL, seconds INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS page_extraction (
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 page INTEGER NOT NULL, method TEXT NOT NULL, PRIMARY KEY(document_id,page)
);
CREATE TABLE IF NOT EXISTS quizzes (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 questions TEXT NOT NULL, results TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classrooms (
 id TEXT PRIMARY KEY, teacher_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL, code_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classroom_members (
 classroom_id TEXT NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 joined_at TEXT NOT NULL, PRIMARY KEY(classroom_id,user_id)
);
CREATE TABLE IF NOT EXISTS class_assignments (
 id TEXT PRIMARY KEY, classroom_id TEXT NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
 title TEXT NOT NULL, questions TEXT NOT NULL, created_at TEXT NOT NULL, due_date TEXT
);
CREATE TABLE IF NOT EXISTS class_submissions (
 assignment_id TEXT NOT NULL REFERENCES class_assignments(id) ON DELETE CASCADE,
 classroom_id TEXT NOT NULL, user_id TEXT NOT NULL, correct INTEGER NOT NULL, total INTEGER NOT NULL,
 submitted_at TEXT NOT NULL, PRIMARY KEY(assignment_id,user_id),
 FOREIGN KEY(classroom_id,user_id) REFERENCES classroom_members(classroom_id,user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_attempt_user ON attempts(user_id,created_at);
CREATE INDEX IF NOT EXISTS idx_read_user ON reading_events(user_id,created_at);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def db_path():
    path = Path(os.environ.get("DECLIC_DB_PATH", str(ROOT / "data" / "declic.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def db():
    con = sqlite3.connect(db_path(), timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with db() as con:
        con.executescript(SCHEMA)


def hash_password(password):
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 360_000)
    return salt.hex() + ":" + derived.hex()


def verify_password(password, stored):
    try:
        salt, digest = stored.split(":")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 360_000), bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def create_user(name, email, password=None):
    uid = uuid.uuid4().hex
    with db() as con:
        con.execute("INSERT INTO users(id,name,email,password_hash,created_at) VALUES(?,?,?,?,?)", (uid,name,email.lower(),hash_password(password) if password else None,now()))
    return uid


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    with db() as con:
        con.execute("INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)", (token_hash,user_id,expires))
    return token


def session_user(token):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as con:
        r = con.execute("SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?", (token_hash,now())).fetchone()
        return dict(r) if r else None


def one(sql, params=()):
    with db() as con:
        r = con.execute(sql, params).fetchone()
        return dict(r) if r else None


def all_rows(sql, params=()):
    with db() as con:
        return [dict(x) for x in con.execute(sql, params).fetchall()]
