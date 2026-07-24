"""Projekt-Routen"""

from flask import Blueprint, jsonify, request

import config
from calendar_utils import q_ord
from database import get_db, project_exists
from history import record_action

bp = Blueprint("projects", __name__)


def _escape_sql(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    return str(val)


@bp.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    try:
        start_year = int(data.get("start_year"))
        start_q = int(data.get("start_q"))
        duration = int(data.get("duration"))
    except (TypeError, ValueError):
        return jsonify({"error": "Ungueltige numerische Werte"}), 400

    if not name or duration < 1 or start_q not in (1, 2, 3, 4):
        return jsonify({"error": "Ungueltige Eingabe"}), 400

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        count = db.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
        color = config.GOOGLE_COLORS[count % len(config.GOOGLE_COLORS)]
        cur = db.execute(
            "INSERT INTO projects (name, start_year, start_q, duration, color) "
            "VALUES (?,?,?,?,?)",
            (name, start_year, start_q, duration, color),
        )
        pid = cur.lastrowid
        db.commit()
    except Exception:
        db.rollback()
        raise

    record_action(
        f"Projekt »{name}« angelegt",
        f"DELETE FROM projects WHERE id = {pid}",
        f"INSERT INTO projects (id, name, start_year, start_q, duration, color) "
        f"VALUES ({pid}, {_escape_sql(name)}, {start_year}, {start_q}, {duration}, {_escape_sql(color)})",
    )
    return jsonify({"id": pid})


@bp.route("/api/projects/<int:project_id>", methods=["PATCH"])
def update_project(project_id):
    db = get_db()
    if not project_exists(db, project_id):
        return jsonify({"error": "Projekt nicht gefunden"}), 404

    old = db.execute(
        "SELECT name, start_year, start_q, duration FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()

    data = request.get_json(force=True)
    fields = {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name darf nicht leer sein"}), 400
        fields["name"] = name
    if "start_year" in data:
        try:
            fields["start_year"] = int(data["start_year"])
        except (TypeError, ValueError):
            return jsonify({"error": "Ungueltiges Jahr"}), 400
    if "start_q" in data:
        try:
            q = int(data["start_q"])
        except (TypeError, ValueError):
            return jsonify({"error": "Ungueltiges Quartal"}), 400
        if q not in (1, 2, 3, 4):
            return jsonify({"error": "Quartal muss 1-4 sein"}), 400
        fields["start_q"] = q
    if "duration" in data:
        try:
            duration = int(data["duration"])
        except (TypeError, ValueError):
            return jsonify({"error": "Ungueltige Dauer"}), 400
        if duration < 1:
            return jsonify({"error": "Dauer muss >= 1 sein"}), 400
        fields["duration"] = duration

    if not fields:
        return jsonify({"error": "Keine Felder zum Aktualisieren"}), 400

    try:
        db.execute("BEGIN IMMEDIATE")

        if "start_year" in fields or "start_q" in fields or "duration" in fields:
            if old:
                new_start_year = fields.get("start_year", old["start_year"])
                new_start_q = fields.get("start_q", old["start_q"])
                new_duration = fields.get("duration", old["duration"])
                new_start_ord = q_ord(new_start_year, new_start_q)
                new_end_ord = new_start_ord + new_duration - 1

                db.execute(
                    """
                    DELETE FROM allocations
                    WHERE project_id = ?
                      AND (year * 4 + (quarter - 1) < ?
                           OR year * 4 + (quarter - 1) > ?)
                    """,
                    (project_id, new_start_ord, new_end_ord),
                )

                db.execute(
                    """
                    DELETE FROM project_steps
                    WHERE project_id = ?
                      AND (start_year * 4 + (start_q - 1) + duration - 1 < ?
                           OR start_year * 4 + (start_q - 1) > ?)
                    """,
                    (project_id, new_start_ord, new_end_ord),
                )

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE projects SET {set_clause} WHERE id = ?",
            (*fields.values(), project_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    new_vals = {k: fields.get(k, old[k]) for k in ("name", "start_year", "start_q", "duration")}
    undo_set = ", ".join(
        f"{k} = {_escape_sql(old[k])}" for k in ("name", "start_year", "start_q", "duration")
    )
    redo_set = ", ".join(
        f"{k} = {_escape_sql(new_vals[k])}" for k in ("name", "start_year", "start_q", "duration")
    )
    record_action(
        f"Projekt »{old['name']}« bearbeitet",
        f"UPDATE projects SET {undo_set} WHERE id = {project_id}",
        f"UPDATE projects SET {redo_set} WHERE id = {project_id}",
    )
    return jsonify({"ok": True})


@bp.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    db = get_db()
    if not project_exists(db, project_id):
        return jsonify({"error": "Projekt nicht gefunden"}), 404

    project = db.execute(
        "SELECT id, name, start_year, start_q, duration, color FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    steps = db.execute(
        "SELECT id, project_id, name, start_year, start_q, duration FROM project_steps WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    allocs = db.execute(
        "SELECT project_id, year, quarter, team_member_id, stunden FROM allocations WHERE project_id = ?",
        (project_id,),
    ).fetchall()

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise

    redo_sql_parts = [f"DELETE FROM projects WHERE id = {project_id}"]

    undo_parts = [
        f"INSERT INTO projects (id, name, start_year, start_q, duration, color) "
        f"VALUES ({project['id']}, {_escape_sql(project['name'])}, "
        f"{project['start_year']}, {project['start_q']}, {project['duration']}, {_escape_sql(project['color'])})"
    ]
    for s in steps:
        undo_parts.append(
            f"INSERT INTO project_steps (id, project_id, name, start_year, start_q, duration) "
            f"VALUES ({s['id']}, {s['project_id']}, {_escape_sql(s['name'])}, "
            f"{s['start_year']}, {s['start_q']}, {s['duration']})"
        )
    for a in allocs:
        undo_parts.append(
            f"INSERT INTO allocations (project_id, year, quarter, team_member_id, stunden) "
            f"VALUES ({a['project_id']}, {a['year']}, {a['quarter']}, {a['team_member_id']}, {a['stunden']})"
        )

    record_action(
        f"Projekt »{project['name']}« gelöscht",
        ";\n".join(undo_parts),
        ";\n".join(redo_sql_parts),
    )
    return jsonify({"ok": True})
