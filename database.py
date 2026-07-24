import shutil
import sqlite3
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import g

import config


def _db_path() -> Path:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return config.DB_PATH


def retry_on_lock(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(config.SQLITE_RETRY_MAX):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                last_exc = exc
                msg = str(exc).lower()
                if "locked" in msg or "busy" in msg:
                    if attempt < config.SQLITE_RETRY_MAX - 1:
                        time.sleep(config.SQLITE_RETRY_BACKOFF * (2 ** attempt))
                        continue
                raise
        raise last_exc

    return wrapper


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(_db_path()))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _column_exists(db, table, column):
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
    return column in cols


@retry_on_lock
def init_db():
    db = sqlite3.connect(str(_db_path()))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            max_stunden_quarter REAL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_year INTEGER NOT NULL,
            start_q INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            color TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS project_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            start_year INTEGER NOT NULL,
            start_q INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            team_member_id INTEGER NOT NULL REFERENCES team_members(id),
            stunden REAL NOT NULL DEFAULT 0,
            UNIQUE(project_id, year, quarter, team_member_id)
        );

        CREATE TABLE IF NOT EXISTS action_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT NOT NULL,
            undo_sql TEXT NOT NULL,
            redo_sql TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS undo_pointer (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_position INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    if not _column_exists(db, "team_members", "max_stunden_quarter"):
        if _column_exists(db, "team_members", "max_tage_quarter"):
            db.execute("ALTER TABLE team_members RENAME COLUMN max_tage_quarter TO max_stunden_quarter")
        else:
            db.execute("ALTER TABLE team_members ADD COLUMN max_stunden_quarter REAL")

    if _column_exists(db, "allocations", "manntage"):
        db.execute("ALTER TABLE allocations RENAME COLUMN manntage TO stunden")

    db.execute("""
        INSERT OR IGNORE INTO undo_pointer (id, current_position)
        VALUES (1, 0)
    """)

    existing = {r["name"] for r in db.execute("SELECT name FROM team_members")}
    for name in config.TEAM_MEMBERS_SEED:
        if name not in existing:
            db.execute("INSERT INTO team_members (name) VALUES (?)", (name,))
    db.commit()
    db.close()


def backup_database():
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = config.BACKUP_DIR / f"kapa_backup_{timestamp}.db"
    src = _db_path()
    if src.exists():
        shutil.copy2(str(src), str(dst))

    backups = sorted(config.BACKUP_DIR.glob("kapa_backup_*.db"))
    while len(backups) > config.BACKUP_MAX_COUNT:
        oldest = backups.pop(0)
        oldest.unlink()

    return dst


# ---------------------------------------------------------------------------
# Datenzugriff (von allen Blueprints verwendbar)
# ---------------------------------------------------------------------------

def fetch_team_members(db):
    return db.execute("SELECT * FROM team_members ORDER BY id").fetchall()


def fetch_projects(db):
    return db.execute(
        "SELECT * FROM projects ORDER BY start_year, start_q, id"
    ).fetchall()


def fetch_steps_by_project(db):
    rows = db.execute(
        "SELECT * FROM project_steps ORDER BY project_id, start_year, start_q, sort_order, id"
    ).fetchall()
    by_project = {}
    for r in rows:
        by_project.setdefault(r["project_id"], []).append(r)
    return by_project


def fetch_allocation_map(db):
    rows = db.execute("SELECT * FROM allocations").fetchall()
    return {
        (r["project_id"], r["year"], r["quarter"], r["team_member_id"]): r[
            "stunden"
        ]
        for r in rows
    }


def project_exists(db, project_id):
    return (
        db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        is not None
    )


def member_exists(db, member_id):
    return (
        db.execute(
            "SELECT 1 FROM team_members WHERE id = ?", (member_id,)
        ).fetchone()
        is not None
    )


def step_exists(db, step_id):
    return (
        db.execute(
            "SELECT 1 FROM project_steps WHERE id = ?", (step_id,)
        ).fetchone()
        is not None
    )


def row_to_dict(row):
    return dict(row)


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
