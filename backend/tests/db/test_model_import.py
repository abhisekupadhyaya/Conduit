def test_account_table_registered_on_metadata():
    from conduit.shared.db import Base
    import conduit.shared.models  # noqa: F401  (must register account)
    t = Base.metadata.tables["account"]
    cols = set(t.columns.keys())
    assert cols == {
        "id", "role", "username", "secret_hash",
        "display_name", "status", "created_at", "updated_at",
    }
