import pytest


def test_password_hash_roundtrip():
    from conduit.core.security import hash_password, verify_password
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"
    assert verify_password("s3cret-pw", h) is True
    assert verify_password("wrong", h) is False


def test_password_long_input_does_not_crash():
    # bcrypt has a 72-byte cap; the helper must guard, not raise.
    from conduit.core.security import hash_password, verify_password
    pw = "a" * 200
    h = hash_password(pw)
    assert verify_password(pw, h) is True


def test_cookie_set_and_clear():
    from fastapi import Response
    from conduit.core.security import set_session_cookie, clear_session_cookie
    r = Response()
    set_session_cookie(r, "tok123")
    sc = r.headers["set-cookie"]
    assert "conduit_session=tok123" in sc
    assert "HttpOnly" in sc
    assert "SameSite=lax" in sc.replace("Lax", "lax")
    r2 = Response()
    clear_session_cookie(r2)
    assert "conduit_session=" in r2.headers["set-cookie"]
    assert ("Max-Age=0" in r2.headers["set-cookie"]) or ("expires=" in r2.headers["set-cookie"].lower())
