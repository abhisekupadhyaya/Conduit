import importlib
import pathlib
import subprocess

# backend/ root: tests/spine/<this file> -> parents[2].
_BACKEND = pathlib.Path(__file__).resolve().parents[2]


def _alembic(*args):
    return subprocess.run([str(_BACKEND / ".venv" / "bin" / "alembic"), *args],
                          cwd=str(_BACKEND), capture_output=True, text=True)


def test_revision_chain():
    """0006 chains directly off 0005_dispatch (mirrors 0005's
    test_down_revision_is_0004_staffing — importlib imports a digit-led
    module fine)."""
    m = importlib.import_module(
        "migrations.versions.0006_conversation_answer_action")
    assert m.down_revision == "0005_dispatch"
    assert m.revision == "0006_conv_aa"


def test_upgrade_downgrade_roundtrips():
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    down = _alembic("downgrade", "0005_dispatch")
    assert down.returncode == 0, down.stderr
    up2 = _alembic("upgrade", "head")
    assert up2.returncode == 0, up2.stderr
