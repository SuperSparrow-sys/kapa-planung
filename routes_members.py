"""Teammitglied-Routen"""

import sqlite3

from flask import Blueprint, jsonify, request

from database import get_db, member_exists

bp = Blueprint("members", __name__)


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
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "Mitarbeiter existiert bereits"}), 400
    except Exception:
        db.rollback()
        raise
    return jsonify({"id": cur.lastrowid, "name": name})


@bp.route("/api/members/<int:member_id>", methods=["PATCH"])
def update_member(member_id):
    if not member_exists(get_db(), member_id):
        return jsonify({"error": "Mitarbeiter nicht gefunden"}), 404

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

    db = get_db()
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
    return jsonify({"ok": True})


@bp.route("/api/members/<int:member_id>", methods=["DELETE"])
def delete_member(member_id):
    if not member_exists(get_db(), member_id):
        return jsonify({"error": "Mitarbeiter nicht gefunden"}), 404

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM allocations WHERE team_member_id = ?", (member_id,))
        db.execute("DELETE FROM team_members WHERE id = ?", (member_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return jsonify({"ok": True})
