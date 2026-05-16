"""The single business-time call site (freezegun-controllable).

Audit columns use DB func.now(); everything business-meaningful
(presence_set_at, the on-shift reference) flows through here.
"""
from __future__ import annotations

import datetime as dt


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
