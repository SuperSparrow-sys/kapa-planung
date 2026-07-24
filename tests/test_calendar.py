from datetime import date

from calendar_utils import (
    current_quarter,
    member_capacity,
    ord_to_q,
    q_label,
    q_ord,
    quarter_bounds,
    workdays_in_quarter,
)


class TestQuarterMath:
    def test_q_ord(self):
        assert q_ord(2025, 1) == 2025 * 4
        assert q_ord(2025, 4) == 2025 * 4 + 3
        assert q_ord(2026, 1) == 2026 * 4

    def test_ord_to_q(self):
        assert ord_to_q(2025 * 4) == (2025, 1)
        assert ord_to_q(2025 * 4 + 3) == (2025, 4)

    def test_roundtrip(self):
        for year in (2024, 2025, 2026):
            for q in (1, 2, 3, 4):
                assert ord_to_q(q_ord(year, q)) == (year, q)

    def test_q_label(self):
        assert q_label(2025, 1) == "25/Q1"
        assert q_label(2026, 4) == "26/Q4"


class TestWorkdays:
    def test_workdays_in_quarter_positive(self):
        wd = workdays_in_quarter(2025, 2)
        assert 55 <= wd <= 68

    def test_workdays_q4_2025(self):
        wd = workdays_in_quarter(2025, 4)
        assert 55 <= wd <= 68

    def test_quarter_bounds(self):
        start, end = quarter_bounds(2025, 1)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 3, 31)

    def test_member_capacity_default(self):
        member = {"max_stunden_quarter": None}
        cap = member_capacity(member, 2025, 2)
        assert cap == 480

    def test_member_capacity_fixed(self):
        member = {"max_stunden_quarter": 42.5}
        cap = member_capacity(member, 2025, 2)
        assert cap == 42.5

    def test_current_quarter(self):
        year, q = current_quarter()
        assert 2020 <= year <= 2100
        assert 1 <= q <= 4
