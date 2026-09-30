"""Shared fixtures. Tests marked ``db`` need the local OMOP Postgres and skip without it."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from oncology_assistant.db import connect


@pytest.fixture(scope="session")
def omop_conn() -> Iterator[psycopg.Connection]:
    """Autocommit connection to the local OMOP database; skips the test if unreachable."""
    try:
        conn = connect()
    except psycopg.OperationalError as exc:
        pytest.skip(f"OMOP database not reachable: {exc}")
    with conn:
        yield conn
