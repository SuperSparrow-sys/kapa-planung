"""Undo/Redo API."""

from flask import Blueprint, jsonify

from history import history_status, redo, undo

bp = Blueprint("history", __name__)


@bp.route("/api/undo", methods=["POST"])
def api_undo():
    return jsonify(undo())


@bp.route("/api/redo", methods=["POST"])
def api_redo():
    return jsonify(redo())


@bp.route("/api/history/status", methods=["GET"])
def api_history_status():
    return jsonify(history_status())
