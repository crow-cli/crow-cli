"""Engine factories: dialect-aware read-only engines + URI normalization.

Real code paths — sqlite RO is enforced by the OS (mode=ro), so the test
actually attempts a write and expects failure. The postgres listener can't
be exercised without a live server (covered by scripts/e2e_postgres_live.py);
here we verify the branch selection and listener wiring.
"""

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from crow_cli.memory import create_database, get_engine, get_ro_engine, normalize_db_uri
from crow_cli.memory.db import _set_pg_readonly


def test_normalize_db_uri_passthrough_and_sqlite():
    assert normalize_db_uri("postgresql+psycopg://u:p@h:5432/crow") == (
        "postgresql+psycopg://u:p@h:5432/crow"
    )
    assert normalize_db_uri("/tmp/x.db") == "sqlite:////tmp/x.db"


def test_sqlite_ro_engine_refuses_writes(tmp_path):
    uri = f"sqlite:///{tmp_path / 'crow.db'}"
    create_database(uri)
    with get_engine(uri).begin() as conn:
        conn.execute(
            text("INSERT INTO prompts(id, name, template, created_at) "
                 "VALUES ('p1', 'n', 't', '2026-01-01T00:00:00+00:00')")
        )

    ro = get_ro_engine(uri)
    assert "mode=ro" in str(ro.url)
    with ro.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM prompts")).scalar() == 1
        with pytest.raises(OperationalError):
            conn.execute(
                text("INSERT INTO prompts(id, name, template, created_at) "
                     "VALUES ('p2', 'n', 't', '2026-01-01T00:00:00+00:00')")
            )


def test_postgres_ro_engine_registers_readonly_listener():
    uri = "postgresql+psycopg://crow:crow@localhost:5432/crow"
    engine = get_ro_engine(uri)  # creation does not connect
    assert engine.url.render_as_string(hide_password=False) == uri
    assert event.contains(engine, "connect", _set_pg_readonly)


def test_postgres_plain_engine_has_no_readonly_listener():
    engine = get_engine("postgresql+psycopg://crow:crow@localhost:5432/crow")
    assert not event.contains(engine, "connect", _set_pg_readonly)
