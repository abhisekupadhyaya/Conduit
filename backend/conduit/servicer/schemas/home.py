# conduit/servicer/schemas/home.py
"""Servicer self schemas (spec §8 "Servicer — self"). ``extra="forbid"``;
no account internals are ever serialized — the derived read only.

§8 shape: ``ServicerHomeOut{profile{class,skills,status},
current_shift?{window,section?,role}, next_shift?, presence,
presence_locked, effective_available}``. The shift "window" is modelled as
explicit ``shift_start``/``shift_end`` (the Roster is the window — Roster
model B, no Shift entity); ``section_label`` is the optional post; ``role``
is the assignment role.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ProfileOut(BaseModel):
    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, serialize_by_alias=True
    )
    # §8 names this field ``class``; ``class`` is a Python keyword, so the
    # attribute is ``class_`` with the on-the-wire alias ``class``.
    class_: str = Field(alias="class")
    skills: list[str]
    status: str


class ShiftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shift_start: dt.datetime
    shift_end: dt.datetime
    section_label: str | None
    role: str


class ServicerHomeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: ProfileOut | None
    skills: list[str]
    current_shift: ShiftOut | None
    next_shift: ShiftOut | None
    presence: str
    presence_locked: bool
    effective_available: bool


class SetPresenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    presence: str
