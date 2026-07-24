"""Teammitglied-Routen"""

import sqlite3

from flask import Blueprint, jsonify, request

from database import get_db, member_exists
from history import record_action

bp = Blueprint("members", __name__)


def _escape_sql(val) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    return str(val)


def _parse_max_stunden_quarter(data):
    if "max_stunden_quarter" not in data:
        return None, False
    val = data.get("max_stunden_quarter")
    if val in (None, ""):
        return None, True
    try:
        return float(val), True
    except (TypeError, ValueError):
        return None, False


@bp.route("/api/members", methods=["POST"])
def create_member():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name darf nicht leer sein"}), 400

    max_stunden_quarter, _ = _parse_max_stunden_quarter(data)

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute(
            "INSERT INTO team_members (name, max_stunden_quarter) VALUES (?,?)",
            (name, max_stunden_quarter),
        )
        mid = cur.lastrowid
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "Mitarbeiter existiert bereits"}), 400
    except Exception:
        db.rollback()
        raise

    record_action(
        f"Mitarbeiter »{name}« angelegt",
        f"DELETE FROM allocations WHERE team_member_id = {mid};\n"
        f"DELETE FROM team_members WHERE id = {mid}",
        f"INSERT INTO team_members (id, name, max_stunden_quarter) "
        f"VALUES ({mid}, {_escape_sql(name)}, {_escape_sql(max_stunden_quarter)})",
    )
    return jsonify({"id": mid, "name": name})


@bp.route("/api/members/<int:member_id>", methods=["PATCH"])
def update_member(member_id):
    db = get_db()
    if not member_exists(db, member_id):
        return jsonify({"error": "Mitarbeiter nicht gefunden"}), 404

    old = db.execute(
        "SELECT name, max_stunden_quarter FROM team_members WHERE id = ?",
        (member_id,),
    ).fetchone()

    data = request.get_json(force=True)
    fields = {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name darf nicht leer sein"}), 400
        fields["name"] = name
    max_stunden_quarter, has_max = _parse_max_stunden_quarter(data)
    if has_max:
        fields["max_stunden_quarter"] = max_stunden_quarter

    if not fields:
        return jsonify({"error": "Keine Felder zum Aktualisieren"}), 400

    try:
        db.execute("BEGIN IMMEDIATE")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        db.execute(
            f"UPDATE team_members SET {set_clause} WHERE id = ?",
            (*fields.values(), member_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "Mitarbeiter existiert bereits"}), 400
    except Exception:
        db.rollback()
        raise

    new_vals = {"name": fields.get("name", old["name"]), "max_stunden_quarter": fields.get("max_stunden_quarter", old["max_stunden_quarter"])}
    undo_set = ", ".join(
        f"{k} = {_escape_sql(old[k])}" for k in ("name", "max_stunden_quarter")
    )
    redo_set = ", ".join(
        f"{k} = {_escape_sql(new_vals[k])}" for k in ("name", "max_stunden_quarter")
    )
    record_action(
        f"Mitarbeiter »{old['name']}« bearbeitet",
        f"UPDATE team_members SET {undo_set} WHERE id = {member_id}",
        f"UPDATE team_members SET {redo_set} WHERE id = {member_id}",
    )
    return jsonify({"ok": True})


@bp.route("/api/members/<int:member_id>", methods=["DELETE"])
def delete_member(member_id):
    db = get_db()
    if not member_exists(db, member_id):
        return jsonify({"error": "Mitarbeiter nicht gefunden"}), 404

    member = db.execute(
        "SELECT id, name, max_stunden_quarter FROM team_members WHERE id = ?",
        (member_id,),
    ).fetchone()
    allocs = db.execute(
        "SELECT project_id, year, quarter, team_member_id, stunden FROM allocations WHERE team_member_id = ?",
        (member_id,),
    ).fetchall()

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM allocations WHERE team_member_id = ?", (member_id,))
        db.execute("DELETE FROM team_members WHERE id = ?", (member_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise

    undo_parts = [
        f"INSERT INTO team_members (id, name, max_stunden_quarter) "
        f"VALUES ({member['id']}, {_escape_sql(member['name'])}, {_escape_sql(member['max_stunden_quarter'])})"
    ]
    for a in allocs:
        undo_parts.append(
            f"INSERT INTO allocations (project_id, year, quarter, team_member_id, stunden) "
            f"VALUES ({a['project_id']}, {a['year']}, {a['quarter']}, {a['team_member_id']}, {a['stunden']})"
        )
    redo_parts = [
        f"DELETE FROM allocations WHERE team_member_id = {member_id}",
        f"DELETE FROM team_members WHERE id = {member_id}",
    ]
    record_action(
        f"Mitarbeiter »{member['name']}« entfernt",
        ";\n".join(undo_parts),
        ";\n".join(redo_parts),
    )
    return jsonify({"ok": True})
