from conduit.core.config import get_settings


def test_conversation_window_default_is_50():
    assert get_settings().conversation_window == 50
