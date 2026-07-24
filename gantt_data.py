"""Bereitet die Gantt-Chart-Daten sowie Auslastungsdaten fuer das Template auf."""

import config
from calendar_utils import (
    current_quarter,
    member_capacity,
    ord_to_q,
    q_label,
    q_ord,
)
from database import (
    fetch_allocation_map,
    fetch_projects,
    fetch_steps_by_project,
    fetch_team_members,
    get_db,
    rows_to_dicts,
)


def prepare_gantt_data():
    db = get_db()
    members = fetch_team_members(db)
    projects = fetch_projects(db)
    steps_by_project = fetch_steps_by_project(db)
    alloc_map = fetch_allocation_map(db)

    cy, cq = current_quarter()
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
        quarters.append(
            {
                "year": y,
                "q": q,
                "label": q_label(y, q),
                "ord": o,
                "is_current": (y, q) == (cy, cq),
            }
        )
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
                    val = alloc_map.get(
                        (entity["id"], qtr["year"], qtr["q"], m["id"]), 0
                    )
                    cell_alloc.append(
                        {
                            "member": m["name"],
                            "member_id": m["id"],
                            "stunden": val,
                        }
                    )
            cells.append(
                {
                    "year": qtr["year"],
                    "q": qtr["q"],
                    "label": qtr["label"],
                    "is_current": qtr["is_current"],
                    "allocations": cell_alloc,
                }
            )
        return cells

    project_rows = []
    for p in projects:
        allocated_total = sum(
            v for (pid, *_), v in alloc_map.items() if pid == p["id"]
        )
        step_rows = []
        for st in steps_by_project.get(p["id"], []):
            step_rows.append({"step": st, "geo": bar_geometry(st)})
        project_rows.append(
            {
                "project": p,
                "geo": bar_geometry(p),
                "cells": active_cells(p, allow_alloc=True),
                "steps": step_rows,
                "allocated_total": round(allocated_total, 1),
            }
        )

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
            per_member.append(
                {
                    "name": m["name"],
                    "total": total,
                    "capacity": cap,
                    "pct": pct,
                    "color": config.GOOGLE_COLORS[idx % len(config.GOOGLE_COLORS)],
                }
            )
        utilization.append(
            {
                "label": qtr["label"],
                "ord": qtr["ord"],
                "is_current": qtr["is_current"],
                "members": per_member,
            }
        )

    opt_start = q_ord(cy, cq)
    opt_end = q_ord(cy, cq) + 40
    quarter_options = []
    for o in range(opt_start, opt_end + 1):
        y, q = ord_to_q(o)
        quarter_options.append({"year": y, "q": q, "label": q_label(y, q)})

    member_defaults = {m["id"]: 480 for m in members}
    members_dicts = rows_to_dicts(members)

    return {
        "quarters": quarters,
        "col_count": col_count,
        "project_rows": project_rows,
        "utilization": utilization,
        "quarter_options": quarter_options,
        "members": members_dicts,
        "member_defaults": member_defaults,
        "current_label": q_label(cy, cq),
        "colors": config.GOOGLE_COLORS,
    }
