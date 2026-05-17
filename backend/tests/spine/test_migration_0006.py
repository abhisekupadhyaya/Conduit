import pathlib
import subprocess

_MIGRATION = (
    "/workspace/Conduit-conversation-answer-action/backend/migrations/"
    "versions/0006_conversation_answer_action.py"
)


def _alembic(*args):
    return subprocess.run(["/workspace/Conduit-conversation-answer-action/"
                           "backend/.venv/bin/alembic", *args],
                          cwd="/workspace/Conduit-conversation-answer-action/"
                          "backend", capture_output=True, text=True)


def test_revision_chain():
    # Textual-assertion form: a module filename starting with ``0006_``
    # cannot be imported via ``import`` / ``importlib`` reliably (the leading
    # digit is not a valid identifier), so assert on the file text directly.
    text = pathlib.Path(_MIGRATION).read_text()
    assert 'down_revision: str | None = "0005_dispatch"' in text
    assert 'revision: str = "0006_conv_aa"' in text


def test_upgrade_downgrade_roundtrips():
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    down = _alembic("downgrade", "0005_dispatch")
    assert down.returncode == 0, down.stderr
    up2 = _alembic("upgrade", "head")
    assert up2.returncode == 0, up2.stderr
