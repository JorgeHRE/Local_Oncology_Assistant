"""Connection to the local OMOP CDM database (see compose.yml and .env.example)."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]


def connect(connect_timeout: int = 3) -> psycopg.Connection:
    """Open an autocommit connection using .env, overridable by environment variables."""
    env = {**dotenv_values(REPO_ROOT / ".env"), **os.environ}
    return psycopg.connect(
        host=env.get("POSTGRES_HOST", "127.0.0.1"),
        port=env.get("POSTGRES_PORT", "5432"),
        user=env.get("POSTGRES_USER", ""),
        password=env.get("POSTGRES_PASSWORD", ""),
        dbname=env.get("POSTGRES_DB", ""),
        autocommit=True,
        connect_timeout=connect_timeout,
    )
