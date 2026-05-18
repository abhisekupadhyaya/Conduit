from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    helpful: bool


class ChildOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: str
    text: str
    issue_code: str | None = None
    issue_label: str | None = None   # D36 embed-derived label (split-echo)
    outcome: str = ""                # triage outcome (.value); additive
    terminal: str               # "answered" | "logged"
    answer: str | None = None
    closure_prompt: bool | None = None
    state: str | None = None


class RequestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    split: bool = False              # D36 split-echo: ≥2 children ⇒ receipt
    children: list[ChildOut]
