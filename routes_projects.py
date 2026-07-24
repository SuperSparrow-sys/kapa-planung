"""Projekt-Routen"""

from flask import Blueprint, jsonify, request

import config
from calendar_utils import q_ord
from database import get_db, project_exists

bp = Blueprint("projects", __name__)


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
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify({"id": cur.lastrowid})


@bp.route("/api/projects/<int:project_id>", methods=["PATCH"])
def update_project(project_id):
    if not project_exists(get_db(), project_id):
        return jsonify({"error": "Projekt nicht gefunden"}), 404

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

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")

        if "start_year" in fields or "start_q" in fields or "duration" in fields:
            project = db.execute(
                "SELECT start_year, start_q, duration FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project:
                new_start_year = fields.get("start_year", project["start_year"])
                new_start_q = fields.get("start_q", project["start_q"])
                new_duration = fields.get("duration", project["duration"])
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
    return jsonify({"ok": True})


@bp.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    if not project_exists(get_db(), project_id):
        return jsonify({"error": "Projekt nicht gefunden"}), 404

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify({"ok": True})
