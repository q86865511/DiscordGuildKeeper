"""ORM models smoke / schema tests.

Verifies that importing :mod:`butler.models` registers every M1 table on
``Base.metadata`` with the spec-mandated names + constraints.
"""

from __future__ import annotations

from butler.models import Base


def test_m1_tables_registered() -> None:
    tables = set(Base.metadata.tables)
    assert {"discord_users", "discord_guilds", "command_invocations"} <= tables


def test_command_invocations_unique_constraint_named() -> None:
    table = Base.metadata.tables["command_invocations"]
    constraint_names = {c.name for c in table.constraints if c.name}
    assert "uq_command_invocations_interaction_id" in constraint_names


def test_discord_users_id_is_bigint_pk() -> None:
    table = Base.metadata.tables["discord_users"]
    pk_cols = list(table.primary_key.columns)
    assert len(pk_cols) == 1
    assert pk_cols[0].name == "id"
    # SQLAlchemy reports the dialect-agnostic type name.
    assert "BIGINT" in str(pk_cols[0].type).upper()


def test_command_invocations_columns_match_spec() -> None:
    table = Base.metadata.tables["command_invocations"]
    expected = {
        "id",
        "interaction_id",
        "guild_id",
        "channel_id",
        "user_id",
        "command_name",
        "status",
        "latency_ms",
        "error_type",
        "error_message",
        "created_at",
    }
    assert set(table.columns.keys()) == expected
