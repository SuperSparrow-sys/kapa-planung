import sqlite3
import calendar
from datetime import date
from functools import lru_cache
from pathlib import Path

from flask import Flask, g, render_template, request, jsonify

import holidays

DB_PATH = Path(__file__).parent / "kapa.db"

app = Flask(__name__)

GOOGLE_COLORS = [
    "#039be5",  # peacock
    "#33b679",  # sage
    "#f4511e",  # tangerine
    "#7986cb",  # lavender
    "#e67c73",  # flamingo
    "#8e24aa",  # grape
    "#f6bf26",  # banana
    "#0b8043",  # basil
    "#d50000",  # tomato
    "#3f51b5",  # blueberry
    "#616161",  # graphite
]

TEAM_MEMBERS_SEED = ["Dominic Meier", "Tony Freudenthal"]


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _column_exists(db, table, column):
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
    return column in cols


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            max_tage_quarter REAL
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
            manntage REAL NOT NULL DEFAULT 0,
            UNIQUE(project_id, year, quarter, team_member_id)
        );
        """
    )
    # Migrationen fuer bereits bestehende kapa.db-Dateien aus aelteren Versionen
    if not _column_exists(db, "team_members", "max_tage_quarter"):
        db.execute("ALTER TABLE team_members ADD COLUMN max_tage_quarter REAL")

    existing = {r["name"] for r in db.execute("SELECT name FROM team_members")}
    for name in TEAM_MEMBERS_SEED:
        if name not in existing:
            db.execute("INSERT INTO team_members (name) VALUES (?)", (name,))
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Quartals- / Kapazitätslogik
# ---------------------------------------------------------------------------

def q_ord(year, q):
    return year * 4 + (q - 1)


def ord_to_q(o):
    year, q = divmod(o, 4)
    return year, q + 1


def q_label(year, q):
    return f"{year % 100:02d}/Q{q}"


def quarter_bounds(year, q):
    start_month = (q - 1) * 3 + 1
    end_month = start_month + 2
    start = date(year, start_month, 1)
    last_day = calendar.monthrange(year, end_month)[1]
    end = date(year, end_month, last_day)
    return start, end


@lru_cache(maxsize=16)
def sachsen_holidays(year):
    return holidays.country_holidays("DE", subdiv="SN", years=year)


@lru_cache(maxsize=256)
def workdays_in_quarter(year, q):
    start, end = quarter_bounds(year, q)
    hol = sachsen_holidays(year)
    count = 0
    cur = start
    one_day = date.resolution
    while cur <= end:
        if cur.weekday() < 5 and cur not in hol:
            count += 1
        cur = cur + one_day
    return count


def member_capacity(member, year, q):
    """Maximale Arbeitstage des Mitarbeiters fuer dieses Quartal.

    Wenn in den Einstellungen ein fester Wert (max_tage_quarter) hinterlegt
    ist, gilt dieser fuer jedes Quartal. Andernfalls wird die Kapazitaet
    automatisch aus den tatsaechlichen Arbeitstagen (abzueglich Feiertage
    Sachsen) berechnet.
    """
    if member["max_tage_quarter"] is not None:
        return member["max_tage_quarter"]
    return workdays_in_quarter(year, q)


def current_quarter():
    today = date.today()
    q = (today.month - 1) // 3 + 1
    return today.year, q


# ---------------------------------------------------------------------------
# Datenzugriff
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
    """{(project_id, year, quarter, team_member_id): manntage}"""
    rows = db.execute("SELECT * FROM allocations").fetchall()
    return {(r["project_id"], r["year"], r["quarter"], r["team_member_id"]): r["manntage"] for r in rows}


# ---------------------------------------------------------------------------
# Routen
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    members = fetch_team_members(db)
    projects = fetch_projects(db)
    steps_by_project = fetch_steps_by_project(db)
    alloc_map = fetch_allocation_map(db)

    cy, cq = current_quarter()
    # Es soll nie ein Quartal vor dem aktuellen angezeigt werden.
    window_start = q_ord(cy, cq)
    window_end = q_ord(cy, cq) + 7

    span_start = window_start
    span_end = window_end
    for p in projects:
        e = q_ord(p["start_year"], p["start_q"]) + p["duration"] - 1
        span_end = max(span_end, e)
    for steps in steps_by_project.values():
        for st in steps:
            e = q_ord(st["start_year"], st["start_q"]) + st["duration"] - 1
            span_end = max(span_end, e)

    quarters = []
    for o in range(span_start, span_end + 1):
        y, q = ord_to_q(o)
        quarters.append({"year": y, "q": q, "label": q_label(y, q), "ord": o,
                          "is_current": (y, q) == (cy, cq)})
    col_count = len(quarters)

    def bar_geometry(entity):
        s_ord = q_ord(entity["start_year"], entity["start_q"])
        e_ord = s_ord + entity["duration"] - 1
        clipped_s = max(s_ord, span_start)
        clipped_e = min(e_ord, span_end)
        left_idx = clipped_s - span_start
        span_count = max(1, clipped_e - clipped_s + 1)
        return {
            "left_idx": left_idx,
            "span_count": span_count,
            "clipped_start": clipped_s > s_ord,
            "clipped_end": clipped_e < e_ord,
        }

    def active_cells(entity, allow_alloc):
        s = q_ord(entity["start_year"], entity["start_q"])
        e = s + entity["duration"] - 1
        cells = []
        for qtr in quarters:
            if not (s <= qtr["ord"] <= e):
                continue
            cell_alloc = None
            if allow_alloc:
                cell_alloc = []
                for m in members:
                    val = alloc_map.get((entity["id"], qtr["year"], qtr["q"], m["id"]), 0)
                    cell_alloc.append({"member": m["name"], "member_id": m["id"], "manntage": val})
            cells.append({
                "year": qtr["year"], "q": qtr["q"], "label": qtr["label"],
                "is_current": qtr["is_current"], "allocations": cell_alloc,
            })
        return cells

    project_rows = []
    for p in projects:
        allocated_total = sum(v for (pid, *_), v in alloc_map.items() if pid == p["id"])
        step_rows = []
        for st in steps_by_project.get(p["id"], []):
            step_rows.append({"step": st, "geo": bar_geometry(st)})
        project_rows.append({
            "project": p,
            "geo": bar_geometry(p),
            "cells": active_cells(p, allow_alloc=True),
            "steps": step_rows,
            "allocated_total": round(allocated_total, 1),
        })

    utilization = []
    for qtr in quarters:
        per_member = []
        for idx, m in enumerate(members):
            total = sum(
                alloc_map.get((p["id"], qtr["year"], qtr["q"], m["id"]), 0)
                for p in projects
            )
            cap = member_capacity(m, qtr["year"], qtr["q"])
            pct = round((total / cap) * 100) if cap else 0
            per_member.append({
                "name": m["name"],
                "total": total,
                "capacity": cap,
                "pct": pct,
                "color": GOOGLE_COLORS[idx % len(GOOGLE_COLORS)],
            })
        utilization.append({"label": qtr["label"], "ord": qtr["ord"],
                             "is_current": qtr["is_current"], "members": per_member})

    opt_start = q_ord(cy, cq)
    opt_end = q_ord(cy, cq) + 40
    quarter_options = []
    for o in range(opt_start, opt_end + 1):
        y, q = ord_to_q(o)
        quarter_options.append({"year": y, "q": q, "label": q_label(y, q)})

    member_defaults = {m["id"]: workdays_in_quarter(cy, cq) for m in members}

    return render_template(
        "index.html",
        quarters=quarters,
        col_count=col_count,
        project_rows=project_rows,
        utilization=utilization,
        colors=GOOGLE_COLORS,
        current_label=q_label(cy, cq),
        quarter_options=quarter_options,
        members=members,
        member_defaults=member_defaults,
    )


# ---------------------------------------------------------------------------
# Projekte
# ---------------------------------------------------------------------------

@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    start_year = int(data.get("start_year"))
    start_q = int(data.get("start_q"))
    duration = int(data.get("duration"))
    if not name or duration < 1 or start_q not in (1, 2, 3, 4):
        return jsonify({"error": "invalid input"}), 400

    db = get_db()
    count = db.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    color = GOOGLE_COLORS[count % len(GOOGLE_COLORS)]
    cur = db.execute(
        "INSERT INTO projects (name, start_year, start_q, duration, color) VALUES (?,?,?,?,?)",
        (name, start_year, start_q, duration, color),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid})


@app.route("/api/projects/<int:project_id>", methods=["PATCH"])
def update_project(project_id):
    data = request.get_json(force=True)
    fields = {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "invalid input"}), 400
        fields["name"] = name
    if "start_year" in data:
        fields["start_year"] = int(data["start_year"])
    if "start_q" in data:
        q = int(data["start_q"])
        if q not in (1, 2, 3, 4):
            return jsonify({"error": "invalid input"}), 400
        fields["start_q"] = q
    if "duration" in data:
        duration = int(data["duration"])
        if duration < 1:
            return jsonify({"error": "invalid input"}), 400
        fields["duration"] = duration

    if not fields:
        return jsonify({"error": "no fields"}), 400

    db = get_db()

    # Wenn sich Start oder Dauer ändert, lösche Einträge für entfallende Quartale
    if "start_year" in fields or "start_q" in fields or "duration" in fields:
        project = db.execute(
            "SELECT start_year, start_q, duration FROM projects WHERE id = ?",
            (project_id,)
        ).fetchone()
        if project:
            new_start_year = fields.get("start_year", project["start_year"])
            new_start_q = fields.get("start_q", project["start_q"])
            new_duration = fields.get("duration", project["duration"])
            new_start_ord = q_ord(new_start_year, new_start_q)
            new_end_ord = new_start_ord + new_duration - 1

            db.execute("""
                DELETE FROM allocations
                WHERE project_id = ?
                  AND (year * 4 + (quarter - 1) < ? OR year * 4 + (quarter - 1) > ?)
            """, (project_id, new_start_ord, new_end_ord))

            # Auch Teilschritte löschen, die außerhalb des neuen Bereichs liegen
            db.execute("""
                DELETE FROM project_steps
                WHERE project_id = ?
                  AND (start_year * 4 + (start_q - 1) + duration - 1 < ?
                       OR start_year * 4 + (start_q - 1) > ?)
            """, (project_id, new_start_ord, new_end_ord))

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", (*fields.values(), project_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Teilschritte
# ---------------------------------------------------------------------------

@app.route("/api/projects/<int:project_id>/steps", methods=["POST"])
def create_step(project_id):
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    start_year = int(data.get("start_year"))
    start_q = int(data.get("start_q"))
    duration = int(data.get("duration"))
    if not name or duration < 1 or start_q not in (1, 2, 3, 4):
        return jsonify({"error": "invalid input"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO project_steps (project_id, name, start_year, start_q, duration) VALUES (?,?,?,?,?)",
        (project_id, name, start_year, start_q, duration),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid})


@app.route("/api/steps/<int:step_id>", methods=["PATCH"])
def update_step(step_id):
    data = request.get_json(force=True)
    fields = {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "invalid input"}), 400
        fields["name"] = name
    if "start_year" in data:
        fields["start_year"] = int(data["start_year"])
    if "start_q" in data:
        q = int(data["start_q"])
        if q not in (1, 2, 3, 4):
            return jsonify({"error": "invalid input"}), 400
        fields["start_q"] = q
    if "duration" in data:
        duration = int(data["duration"])
        if duration < 1:
            return jsonify({"error": "invalid input"}), 400
        fields["duration"] = duration

    if not fields:
        return jsonify({"error": "no fields"}), 400

    db = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE project_steps SET {set_clause} WHERE id = ?", (*fields.values(), step_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/steps/<int:step_id>", methods=["DELETE"])
def delete_step(step_id):
    db = get_db()
    db.execute("DELETE FROM project_steps WHERE id = ?", (step_id,))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Teammitglieder (Einstellungen) — inkl. max. Tage pro Quartal
# ---------------------------------------------------------------------------

def _parse_max_tage_quarter(data):
    if "max_tage_quarter" not in data:
        return None, False
    val = data.get("max_tage_quarter")
    if val in (None, ""):
        return None, True
    return float(val), True


@app.route("/api/members", methods=["POST"])
def create_member():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "invalid input"}), 400
    max_tage_quarter, _ = _parse_max_tage_quarter(data)
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO team_members (name, max_tage_quarter) VALUES (?,?)",
            (name, max_tage_quarter),
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "Mitarbeiter existiert bereits"}), 400
    db.commit()
    return jsonify({"id": cur.lastrowid, "name": name})


@app.route("/api/members/<int:member_id>", methods=["PATCH"])
def update_member(member_id):
    data = request.get_json(force=True)
    fields = {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "invalid input"}), 400
        fields["name"] = name
    max_tage_quarter, has_max = _parse_max_tage_quarter(data)
    if has_max:
        fields["max_tage_quarter"] = max_tage_quarter

    if not fields:
        return jsonify({"error": "no fields"}), 400

    db = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    try:
        db.execute(f"UPDATE team_members SET {set_clause} WHERE id = ?", (*fields.values(), member_id))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Mitarbeiter existiert bereits"}), 400
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/members/<int:member_id>", methods=["DELETE"])
def delete_member(member_id):
    db = get_db()
    db.execute("DELETE FROM allocations WHERE team_member_id = ?", (member_id,))
    db.execute("DELETE FROM team_members WHERE id = ?", (member_id,))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Manntage
# ---------------------------------------------------------------------------

@app.route("/api/allocations", methods=["POST"])
def save_allocation():
    data = request.get_json(force=True)
    project_id = int(data["project_id"])
    year = int(data["year"])
    quarter = int(data["quarter"])
    values = data.get("values", {})  # {member_id: manntage}

    db = get_db()
    for member_id, manntage in values.items():
        manntage = float(manntage or 0)
        db.execute(
            """
            INSERT INTO allocations (project_id, year, quarter, team_member_id, manntage)
            VALUES (?,?,?,?,?)
            ON CONFLICT(project_id, year, quarter, team_member_id)
            DO UPDATE SET manntage = excluded.manntage
            """,
            (project_id, year, quarter, int(member_id), manntage),
        )
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5050)
