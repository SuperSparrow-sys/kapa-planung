"""Teilschritt-Routen"""

from flask import Blueprint, jsonify, request

from database import get_db, project_exists, step_exists
from history import record_action

bp = Blueprint("steps", __name__)


def _escape_sql(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    return str(val)


@bp.route("/api/projects/<int:project_id>/steps", methods=["POST"])
def create_step(project_id):
    if not project_exists(get_db(), project_id):
        return jsonify({"error": "Projekt nicht gefunden"}), 404

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
        cur = db.execute(
            "INSERT INTO project_steps (project_id, name, start_year, start_q, duration) "
            "VALUES (?,?,?,?,?)",
            (project_id, name, start_year, start_q, duration),
        )
        sid = cur.lastrowid
        db.commit()
    except Exception:
        db.rollback()
        raise

    record_action(
        f"Teilschritt »{name}« angelegt",
        f"DELETE FROM project_steps WHERE id = {sid}",
        f"INSERT INTO project_steps (id, project_id, name, start_year, start_q, duration) "
        f"VALUES ({sid}, {project_id}, {_escape_sql(name)}, {start_year}, {start_q}, {duration})",
    )
    return jsonify({"id": sid})


@bp.route("/api/steps/<int:step_id>", methods=["PATCH"])
def update_step(step_id):
    db = get_db()
    if not step_exists(db, step_id):
        return jsonify({"error": "Teilschritt nicht gefunden"}), 404

    old = db.execute(
        "SELECT name, start_year, start_q, duration FROM project_steps WHERE id = ?",
        (step_id,),
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
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE project_steps SET {set_clause} WHERE id = ?",
            (*fields.values(), step_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    undo_set = ", ".join(
        f"{k} = {_escape_sql(old[k])}" for k in ("name", "start_year", "start_q", "duration")
    )
    new_vals = {k: fields.get(k, old[k]) for k in ("name", "start_year", "start_q", "duration")}
    redo_set = ", ".join(
        f"{k} = {_escape_sql(new_vals[k])}" for k in ("name", "start_year", "start_q", "duration")
    )
    record_action(
        f"Teilschritt »{old['name']}« bearbeitet",
        f"UPDATE project_steps SET {undo_set} WHERE id = {step_id}",
        f"UPDATE project_steps SET {redo_set} WHERE id = {step_id}",
    )
    return jsonify({"ok": True})


@bp.route("/api/steps/<int:step_id>", methods=["DELETE"])
def delete_step(step_id):
    db = get_db()
    if not step_exists(db, step_id):
        return jsonify({"error": "Teilschritt nicht gefunden"}), 404

    step = db.execute(
        "SELECT id, project_id, name, start_year, start_q, duration FROM project_steps WHERE id = ?",
        (step_id,),
    ).fetchone()

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM project_steps WHERE id = ?", (step_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise

    record_action(
        f"Teilschritt »{step['name']}« gelöscht",
        f"INSERT INTO project_steps (id, project_id, name, start_year, start_q, duration) "
        f"VALUES ({step['id']}, {step['project_id']}, {_escape_sql(step['name'])}, "
        f"{step['start_year']}, {step['start_q']}, {step['duration']})",
        f"DELETE FROM project_steps WHERE id = {step_id}",
    )
    return jsonify({"ok": True})
