import calendar
from datetime import date
from functools import lru_cache

import holidays


def q_ord(year, q):
    return year * 4 + (q - 1)


def ord_to_q(o):
    year, q = divmod(o, 4)
    return year, q + 1


def q_label(year, q):
    return f"{year % 100:02d}/Q{q}"


def quarter_bounds(year, q):
    start_month = (q - 1) * 3 + 1
    end_month = start_month + 2
    start = date(year, start_month, 1)
    last_day = calendar.monthrange(year, end_month)[1]
    end = date(year, end_month, last_day)
    return start, end


@lru_cache(maxsize=16)
def sachsen_holidays(year):
    return holidays.country_holidays("DE", subdiv="SN", years=year)


@lru_cache(maxsize=256)
def workdays_in_quarter(year, q):
    start, end = quarter_bounds(year, q)
    hol = sachsen_holidays(year)
    count = 0
    cur = start
    one_day = date.resolution
    while cur <= end:
        if cur.weekday() < 5 and cur not in hol:
            count += 1
        cur = cur + one_day
    return count


def member_capacity(member, year, q):
    if member["max_stunden_quarter"] is not None:
        return member["max_stunden_quarter"]
    return 480


def current_quarter():
    today = date.today()
    q = (today.month - 1) // 3 + 1
    return today.year, q
