import importlib
import pathlib
import subprocess

from sqlalchemy import inspect

from conduit.shared.models import IssueCode, WorkOrder, RecRelocate  # noqa: F401

# backend/ root: tests/spine/<this file> -> parents[2].
_BACKEND = pathlib.Path(__file__).resolve().parents[2]


def _alembic(*args):
    return subprocess.run([str(_BACKEND / ".venv" / "bin" / "alembic"), *args],
                          cwd=str(_BACKEND), capture_output=True, text=True)


def test_revision_chain():
    m = importlib.import_module(
        "migrations.versions.0007_relocation_subflow")
    assert m.down_revision == "0006_conv_aa"
    assert m.revision == "0007_relocation_subflow"


def test_issue_code_has_origin():
    assert "origin" in {c.name for c in inspect(IssueCode).columns}


def test_recrelocate_unchanged_populate_not_add():
    assert {c.name for c in inspect(RecRelocate).columns} == {
        "recommendation_escalation_id", "target_room_id"}


def test_upgrade_downgrade_roundtrips():
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    down = _alembic("downgrade", "0006_conv_aa")
    assert down.returncode == 0, down.stderr
    up2 = _alembic("upgrade", "head")
    assert up2.returncode == 0, up2.stderr
