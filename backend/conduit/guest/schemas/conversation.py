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
    terminal: str               # "answered" | "logged"
    answer: str | None = None
    closure_prompt: bool | None = None
    state: str | None = None


class RequestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    children: list[ChildOut]
