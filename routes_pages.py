"""Seiten-Routen (GET /)"""

from flask import Blueprint, jsonify, render_template

from gantt_data import prepare_gantt_data

bp = Blueprint("pages", __name__)


@bp.route("/")
def index():
    data = prepare_gantt_data()
    return render_template("index.html", **data)


@bp.route("/_partial")
def partial():
    data = prepare_gantt_data()
    sidebar_html = render_template("_sidebar.html", **data)
    gantt_html = render_template("_gantt.html", **data)
    return jsonify(
        {
            "sidebar": sidebar_html,
            "gantt": gantt_html,
            "quarter_options": data["quarter_options"],
            "members": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "max_stunden_quarter": m["max_stunden_quarter"],
                }
                for m in data["members"]
            ],
            "member_defaults": data["member_defaults"],
        }
    )
