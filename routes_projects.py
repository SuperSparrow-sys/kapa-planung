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

    # ── Alten Zustand aller Schritte + Allokationen sichern (für Undo) ──
    old_steps = db.execute(
        "SELECT id, project_id, name, start_year, start_q, duration FROM project_steps WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    old_allocs = db.execute(
        "SELECT project_id, year, quarter, team_member_id, stunden FROM allocations WHERE project_id = ?",
        (project_id,),
    ).fetchall()

    try:
        db.execute("BEGIN IMMEDIATE")

        if "start_year" in fields or "start_q" in fields or "duration" in fields:
            project = db.execute(
                "SELECT start_year, start_q, duration FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project:
                old_start_ord = q_ord(project["start_year"], project["start_q"])
                new_start_year = fields.get("start_year", project["start_year"])
                new_start_q = fields.get("start_q", project["start_q"])
                delta = q_ord(new_start_year, new_start_q) - old_start_ord

                if delta != 0:
                    # ── Allokationen verschieben (DELETE + INSERT, vermeidet UNIQUE-Konflikt) ──
                    allocs = db.execute(
                        "SELECT project_id, year, quarter, team_member_id, stunden "
                        "FROM allocations WHERE project_id = ?",
                        (project_id,),
                    ).fetchall()
                    db.execute("DELETE FROM allocations WHERE project_id = ?", (project_id,))
                    for a in allocs:
                        new_ord = a["year"] * 4 + (a["quarter"] - 1) + delta
                        ny, nq = divmod(new_ord, 4)
                        nq += 1
                        db.execute(
                            "INSERT INTO allocations (project_id, year, quarter, team_member_id, stunden) "
                            "VALUES (?,?,?,?,?)",
                            (project_id, ny, nq, a["team_member_id"], a["stunden"]),
                        )

                    # ── Teilschritte verschieben ──
                    db.execute(
                        """
                        UPDATE project_steps
                        SET start_year = CAST((start_year * 4 + (start_q - 1) + ?) / 4 AS INTEGER),
                            start_q = ((start_year * 4 + (start_q - 1) + ?) % 4) + 1
                        WHERE project_id = ?
                        """,
                        (delta, delta, project_id),
                    )

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

    new_vals = {k: fields.get(k, old[k]) for k in ("name", "start_year", "start_q", "duration")}
    undo_sql_parts = [
        f"UPDATE projects SET name={_escape_sql(old['name'])}, "
        f"start_year={old['start_year']}, start_q={old['start_q']}, "
        f"duration={old['duration']} WHERE id = {project_id}"
    ]
    redo_sql_parts = [
        f"UPDATE projects SET name={_escape_sql(new_vals['name'])}, "
        f"start_year={new_vals['start_year']}, start_q={new_vals['start_q']}, "
        f"duration={new_vals['duration']} WHERE id = {project_id}"
    ]

    # Undo: alte Schritte+Allokationen wiederherstellen (DELETE + INSERT)
    undo_sql_parts.append(f"DELETE FROM project_steps WHERE project_id = {project_id}")
    for s in old_steps:
        undo_sql_parts.append(
            f"INSERT INTO project_steps (id, project_id, name, start_year, start_q, duration) "
            f"VALUES ({s['id']}, {s['project_id']}, {_escape_sql(s['name'])}, "
            f"{s['start_year']}, {s['start_q']}, {s['duration']})"
        )
    undo_sql_parts.append(f"DELETE FROM allocations WHERE project_id = {project_id}")
    for a in old_allocs:
        undo_sql_parts.append(
            f"INSERT INTO allocations (project_id, year, quarter, team_member_id, stunden) "
            f"VALUES ({a['project_id']}, {a['year']}, {a['quarter']}, {a['team_member_id']}, {a['stunden']})"
        )

    # Redo: aktuelle Schritte+Allokationen wiederherstellen
    new_steps = db.execute(
        "SELECT id, project_id, name, start_year, start_q, duration FROM project_steps WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    new_allocs = db.execute(
        "SELECT project_id, year, quarter, team_member_id, stunden FROM allocations WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    redo_sql_parts.append(f"DELETE FROM project_steps WHERE project_id = {project_id}")
    for s in new_steps:
        redo_sql_parts.append(
            f"INSERT INTO project_steps (id, project_id, name, start_year, start_q, duration) "
            f"VALUES ({s['id']}, {s['project_id']}, {_escape_sql(s['name'])}, "
            f"{s['start_year']}, {s['start_q']}, {s['duration']})"
        )
    redo_sql_parts.append(f"DELETE FROM allocations WHERE project_id = {project_id}")
    for a in new_allocs:
        redo_sql_parts.append(
            f"INSERT INTO allocations (project_id, year, quarter, team_member_id, stunden) "
            f"VALUES ({a['project_id']}, {a['year']}, {a['quarter']}, {a['team_member_id']}, {a['stunden']})"
        )

    action_desc = f"Projekt »{old['name']}« bearbeitet"
    if "start_year" in fields or "start_q" in fields:
        action_desc = f"Projekt »{old['name']}« verschoben"
    record_action(
        action_desc,
        ";\n".join(undo_sql_parts),
        ";\n".join(redo_sql_parts),
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
