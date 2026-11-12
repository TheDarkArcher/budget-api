"""Tests for the backup and restore script, against a real PostgreSQL.

They run ``pg_dump`` and ``pg_restore`` in the tests' own Postgres container,
on scratch databases, so they never touch the database other tests use.
"""

import logging
import re
import stat
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import backups
import pytest
from backups import (
    DatabaseCommandError,
    RestoreError,
    backup,
    main,
    restore,
)
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

DATABASE = "backup_scratch"
OLD_ASIDE = "backup_scratch_before_restore_20000101T000000"
# Every scratch database these tests create starts with DATABASE.
SCRATCH_DATABASES = r"backup\_scratch%"


def dump_database_name(path: Path) -> str:
    with path.open("rb") as dump:
        return backups._read_database_name(dump, path)


def notes(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(text("SELECT name FROM notes ORDER BY name")).scalars()
        )


def add_note(engine: Engine, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO notes (name) VALUES (:name)"), {"name": name}
        )


def scratch_databases(admin: Engine) -> list[str]:
    with admin.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT datname FROM pg_database WHERE datname LIKE :pattern"
                    " ORDER BY datname"
                ),
                {"pattern": SCRATCH_DATABASES},
            ).scalars()
        )


def container_command(
    postgres: PostgresContainer, database: str = DATABASE
) -> tuple[str, ...]:
    # Runs a command in the tests' Postgres container, which sees `database`
    # as its POSTGRES_DB, so a backup dumps that database.
    container_id = postgres.get_wrapped_container().id
    # docker's untyped id could be None as far as type checkers can tell, but
    # a started container always has one.
    assert container_id is not None
    return (
        "docker",
        "exec",
        "-i",
        "-e",
        f"POSTGRES_DB={database}",
        container_id,
    )


def make_restores_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    # Runs every command for real, then reports `pg_restore --create` as
    # failed, after it has already created and filled the new database. The
    # wrapper finds the container's script among its arguments.
    monkeypatch.setattr(
        backups,
        "COMPOSE_DB",
        (
            "sh",
            "-c",
            '"$@"; status=$?; for arg; do case "$arg" in "pg_restore --create"*) '
            'echo "restore failed" >&2; exit 1;; esac; done; exit $status',
            "wrapper",
            *backups.COMPOSE_DB,
        ),
    )


def interrupted_after_restore(real_run: Callable[..., str]) -> Callable[..., str]:
    # Runs every command for real, then raises KeyboardInterrupt, as Ctrl-C
    # would, once `pg_restore --create` has created and filled the database.
    def run(script: str, *args: str, **kwargs: Any) -> str:
        output = real_run(script, *args, **kwargs)
        if script.startswith("pg_restore --create"):
            raise KeyboardInterrupt
        return output

    return run


def record_psql(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    # Runs psql for real and records each statement, so a test can see
    # whether the existing database was renamed aside or dropped.
    statements: list[str] = []
    real_psql = backups._psql

    def recording_psql(sql: str, **variables: str) -> str:
        statements.append(sql)
        return real_psql(sql, **variables)

    monkeypatch.setattr(backups, "_psql", recording_psql)
    return statements


def make_empty(scratch: Engine) -> None:
    # Leaves the scratch database as empty as a newly created one.
    with scratch.begin() as connection:
        connection.execute(text("DROP TABLE notes"))


def database_oid(admin: Engine) -> int:
    # Changes whenever the scratch database is dropped and created again.
    with admin.connect() as connection:
        oid: int = connection.execute(
            text("SELECT oid FROM pg_database WHERE datname = :name"),
            {"name": DATABASE},
        ).scalar_one()
    return oid


@pytest.fixture(autouse=True)
def use_test_container(
    postgres: PostgresContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Points the script at the tests' container, and its dumps at a
    # temporary folder.
    monkeypatch.setattr(backups, "COMPOSE_DB", container_command(postgres))
    monkeypatch.setattr(backups, "BACKUPS_DIR", tmp_path / "backups")


@pytest.fixture
def admin(postgres: PostgresContainer) -> Iterator[Engine]:
    url = make_url(postgres.get_connection_url()).set(drivername="postgresql+psycopg")
    engine = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture
def scratch(postgres: PostgresContainer, admin: Engine) -> Iterator[Engine]:
    url = make_url(postgres.get_connection_url()).set(
        drivername="postgresql+psycopg", database=DATABASE
    )
    engine = create_engine(url, poolclass=NullPool)
    try:
        with admin.connect() as connection:
            connection.execute(text("CREATE DATABASE backup_scratch"))
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE notes (name text NOT NULL)"))
        add_note(engine, "original")
        yield engine
    finally:
        engine.dispose()
        # Drops every scratch database, including set-aside copies, whatever
        # state a test left them in. It goes through the admin connection
        # rather than the script, so a test's patches can't get in the way.
        with admin.connect() as connection:
            drops = (
                connection.execute(
                    text(
                        "SELECT format('DROP DATABASE %I WITH (FORCE)', datname)"
                        " FROM pg_database WHERE datname LIKE :pattern"
                    ),
                    {"pattern": SCRATCH_DATABASES},
                )
                .scalars()
                .all()
            )
            for drop in drops:
                connection.exec_driver_sql(drop)


@pytest.fixture
def dump(scratch: Engine) -> Path:
    return backup()


def test_backup_writes_a_timestamped_dump_of_the_database(
    dump: Path,
) -> None:
    assert dump.parent == backups.BACKUPS_DIR
    assert re.fullmatch(r"db_backup_\d{8}T\d{6}\.dump", dump.name)
    assert dump_database_name(dump) == DATABASE


def test_backup_is_readable_only_by_its_owner(dump: Path) -> None:
    assert stat.S_IMODE(dump.stat().st_mode) == 0o600


@pytest.mark.usefixtures("scratch")
def test_backup_creates_the_folder() -> None:
    assert not backups.BACKUPS_DIR.exists()
    assert backup().parent == backups.BACKUPS_DIR


def test_a_failed_backup_leaves_no_file(
    postgres: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        backups, "COMPOSE_DB", container_command(postgres, "no_such_database")
    )
    with pytest.raises(DatabaseCommandError):
        backup()
    assert list(backups.BACKUPS_DIR.iterdir()) == []


def test_an_interrupted_backup_leaves_no_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(*args: object, **kwargs: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(backups, "_run", interrupt)
    with pytest.raises(KeyboardInterrupt):
        backup()
    assert list(backups.BACKUPS_DIR.iterdir()) == []


@pytest.mark.usefixtures("scratch")
def test_a_second_backup_in_the_same_second_keeps_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backups, "_timestamp", lambda: "20261111T143000")
    first = backup()
    size = first.stat().st_size
    with pytest.raises(FileExistsError):
        backup()
    assert first.stat().st_size == size > 0


def test_restores_into_a_missing_database(
    dump: Path, scratch: Engine, admin: Engine
) -> None:
    with admin.connect() as connection:
        connection.execute(text("DROP DATABASE backup_scratch"))
    assert restore(dump) == DATABASE
    assert notes(scratch) == ["original"]
    assert scratch_databases(admin) == [DATABASE]


def test_drops_an_empty_database_rather_than_setting_it_aside(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_empty(scratch)
    statements = record_psql(monkeypatch)
    restore(dump)
    assert notes(scratch) == ["original"]
    assert scratch_databases(admin) == [DATABASE]
    assert not any("RENAME" in statement for statement in statements)
    assert 'DROP DATABASE :"database";' in statements


def test_a_failed_restore_over_an_empty_database_leaves_it_empty(
    dump: Path, scratch: Engine, admin: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_empty(scratch)
    oid = database_oid(admin)
    make_restores_fail(monkeypatch)
    with pytest.raises(RestoreError, match="nothing was changed"):
        restore(dump)
    assert scratch_databases(admin) == [DATABASE]
    # Dropped and created again, empty.
    assert database_oid(admin) != oid
    assert backups._is_empty(DATABASE)


def test_a_new_database_counts_as_empty(scratch: Engine) -> None:
    make_empty(scratch)
    assert backups._is_empty(DATABASE)


# Each case leaves one object in the otherwise empty scratch database.
@pytest.mark.parametrize(
    "sql",
    [
        pytest.param("CREATE TABLE things (id int)", id="table"),
        pytest.param("CREATE VIEW one AS SELECT 1 AS one", id="view"),
        pytest.param("CREATE SEQUENCE counter", id="sequence"),
        pytest.param(
            "CREATE FUNCTION one() RETURNS int LANGUAGE sql AS 'SELECT 1'",
            id="function",
        ),
        pytest.param("CREATE TYPE mood AS ENUM ('happy')", id="type"),
        pytest.param("CREATE SCHEMA extra", id="schema"),
        pytest.param("CREATE EXTENSION pg_trgm", id="extension"),
        pytest.param("SELECT lo_create(0)", id="large object"),
    ],
)
def test_any_object_counts_as_not_empty(scratch: Engine, sql: str) -> None:
    make_empty(scratch)
    with scratch.begin() as connection:
        connection.execute(text(sql))
    assert not backups._is_empty(DATABASE)


def test_a_database_that_cant_be_checked_counts_as_not_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert not backups._is_empty("no_such_database")
    assert 'Couldn\'t check whether "no_such_database" is empty' in caplog.text


def test_a_failed_drop_of_an_empty_database_changes_nothing(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_empty(scratch)
    oid = database_oid(admin)
    real_psql = backups._psql

    def failing_drop(sql: str, **variables: str) -> str:
        if sql == 'DROP DATABASE :"database";':
            raise DatabaseCommandError("drop failed")
        return real_psql(sql, **variables)

    monkeypatch.setattr(backups, "_psql", failing_drop)
    with pytest.raises(RestoreError, match="Couldn't replace the empty database"):
        restore(dump)
    assert database_oid(admin) == oid


def test_a_failed_recreate_says_no_data_was_lost(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_empty(scratch)
    real_psql = backups._psql

    def failing_create(sql: str, **variables: str) -> str:
        if sql.startswith("CREATE DATABASE"):
            raise DatabaseCommandError("create failed")
        return real_psql(sql, **variables)

    monkeypatch.setattr(backups, "_psql", failing_create)
    make_restores_fail(monkeypatch)
    with pytest.raises(RestoreError, match="was empty, so no data was lost"):
        restore(dump)
    assert scratch_databases(admin) == []


def test_an_interrupted_restore_over_an_empty_database_leaves_it_empty(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_empty(scratch)
    oid = database_oid(admin)
    monkeypatch.setattr(backups, "_run", interrupted_after_restore(backups._run))
    with pytest.raises(KeyboardInterrupt):
        restore(dump)
    assert scratch_databases(admin) == [DATABASE]
    assert database_oid(admin) != oid
    assert backups._is_empty(DATABASE)


def test_an_empty_database_with_a_long_name_isnt_refused(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only a database that's set aside needs a name short enough for that.
    make_empty(scratch)
    monkeypatch.setattr(backups, "_timestamp", lambda: "x" * 40)
    restore(dump)
    assert notes(scratch) == ["original"]
    assert scratch_databases(admin) == [DATABASE]


def test_refuses_a_database_with_data_without_force(
    dump: Path, scratch: Engine, admin: Engine
) -> None:
    add_note(scratch, "changed")
    with pytest.raises(RestoreError, match="--force"):
        restore(dump)
    assert notes(scratch) == ["changed", "original"]
    assert scratch_databases(admin) == [DATABASE]


def test_force_replaces_the_database(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_note(scratch, "changed")
    statements = record_psql(monkeypatch)
    restore(dump, force=True)
    assert notes(scratch) == ["original"]
    assert scratch_databases(admin) == [DATABASE]
    # Set aside rather than dropped, since it wasn't empty.
    assert any("RENAME" in statement for statement in statements)


def test_refuses_a_database_that_is_in_use(
    dump: Path, scratch: Engine, admin: Engine
) -> None:
    add_note(scratch, "changed")
    with scratch.connect(), pytest.raises(RestoreError, match="stop the app"):
        restore(dump, force=True)
    assert notes(scratch) == ["changed", "original"]
    assert scratch_databases(admin) == [DATABASE]


def test_sets_the_database_aside_under_a_timestamped_name(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A copy left by an earlier failed restore neither blocks this restore
    # nor is touched by it.
    with admin.connect() as connection:
        connection.execute(
            text('CREATE DATABASE "backup_scratch_before_restore_20000101T000000"')
        )
    monkeypatch.setattr(backups, "_timestamp", lambda: "20261111T143000")
    set_aside: list[str] = []
    real_psql = backups._psql

    def recording_psql(sql: str, **variables: str) -> str:
        if "aside" in variables:
            set_aside.append(variables["aside"])
        return real_psql(sql, **variables)

    monkeypatch.setattr(backups, "_psql", recording_psql)
    restore(dump, force=True)
    assert set(set_aside) == {"backup_scratch_before_restore_20261111T143000"}
    assert notes(scratch) == ["original"]
    assert scratch_databases(admin) == [DATABASE, OLD_ASIDE]


def test_a_failed_restore_keeps_the_original_database(
    dump: Path, scratch: Engine, admin: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_note(scratch, "changed")
    make_restores_fail(monkeypatch)
    with pytest.raises(RestoreError, match="nothing was changed"):
        restore(dump, force=True)
    assert notes(scratch) == ["changed", "original"]
    assert scratch_databases(admin) == [DATABASE]


def test_a_failed_restore_into_a_missing_database_leaves_nothing(
    dump: Path, admin: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with admin.connect() as connection:
        connection.execute(text("DROP DATABASE backup_scratch"))
    make_restores_fail(monkeypatch)
    with pytest.raises(RestoreError, match="nothing was changed"):
        restore(dump)
    assert scratch_databases(admin) == []


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(DatabaseCommandError("rename failed"), id="database error"),
        pytest.param(PermissionError("can't start the command"), id="os error"),
    ],
)
def test_a_failed_undo_says_where_the_original_data_is(
    dump: Path,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    monkeypatch.setattr(backups, "_timestamp", lambda: "20261111T143000")
    real_psql = backups._psql

    def failing_rename_back(sql: str, **variables: str) -> str:
        if sql.startswith('ALTER DATABASE :"aside"'):
            raise error
        return real_psql(sql, **variables)

    monkeypatch.setattr(backups, "_psql", failing_rename_back)
    aside = "backup_scratch_before_restore_20261111T143000"
    make_restores_fail(monkeypatch)
    with pytest.raises(RestoreError, match=f'safe in the database "{aside}"'):
        restore(dump, force=True)
    assert scratch_databases(admin) == [aside]


def test_refuses_a_name_too_long_to_set_aside(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A timestamp long enough to push the set-aside name past 63 bytes.
    monkeypatch.setattr(backups, "_timestamp", lambda: "x" * 40)
    add_note(scratch, "changed")
    with pytest.raises(RestoreError, match="too long"):
        restore(dump, force=True)
    assert notes(scratch) == ["changed", "original"]
    assert scratch_databases(admin) == [DATABASE]


def test_an_interrupted_restore_puts_the_original_back(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backups, "_run", interrupted_after_restore(backups._run))
    add_note(scratch, "changed")
    with pytest.raises(KeyboardInterrupt):
        restore(dump, force=True)
    assert notes(scratch) == ["changed", "original"]
    assert scratch_databases(admin) == [DATABASE]


def test_a_dump_that_cant_be_opened_changes_nothing(
    scratch: Engine, admin: Engine, tmp_path: Path
) -> None:
    add_note(scratch, "changed")
    with pytest.raises(RestoreError, match=r"Couldn't open .*nothing was changed"):
        restore(tmp_path / "missing.dump", force=True)
    assert notes(scratch) == ["changed", "original"]
    assert scratch_databases(admin) == [DATABASE]


def test_an_interrupted_restore_into_a_missing_database_leaves_nothing(
    dump: Path,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with admin.connect() as connection:
        connection.execute(text("DROP DATABASE backup_scratch"))
    monkeypatch.setattr(backups, "_run", interrupted_after_restore(backups._run))
    with pytest.raises(KeyboardInterrupt):
        restore(dump)
    assert scratch_databases(admin) == []


def test_an_interrupted_restore_reports_a_failed_undo(
    dump: Path,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(backups, "_timestamp", lambda: "20261111T143000")
    monkeypatch.setattr(backups, "_run", interrupted_after_restore(backups._run))
    real_psql = backups._psql

    def failing_rename_back(sql: str, **variables: str) -> str:
        if sql.startswith('ALTER DATABASE :"aside"'):
            raise DatabaseCommandError("rename failed")
        return real_psql(sql, **variables)

    monkeypatch.setattr(backups, "_psql", failing_rename_back)
    aside = "backup_scratch_before_restore_20261111T143000"
    with pytest.raises(KeyboardInterrupt):
        restore(dump, force=True)
    assert f'safe in the database "{aside}"' in caplog.text
    assert scratch_databases(admin) == [aside]


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(DatabaseCommandError("drop failed"), id="database error"),
        pytest.param(PermissionError("can't start the command"), id="os error"),
    ],
)
def test_a_failed_clean_up_still_counts_as_restored(
    dump: Path,
    scratch: Engine,
    admin: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    monkeypatch.setattr(backups, "_timestamp", lambda: "20261111T143000")
    real_psql = backups._psql

    def failing_drop_aside(sql: str, **variables: str) -> str:
        if sql.startswith('DROP DATABASE :"aside"'):
            raise error
        return real_psql(sql, **variables)

    monkeypatch.setattr(backups, "_psql", failing_drop_aside)
    add_note(scratch, "changed")
    assert restore(dump, force=True) == DATABASE
    assert notes(scratch) == ["original"]
    assert "couldn't drop the set-aside copy" in caplog.text
    assert scratch_databases(admin) == [
        DATABASE,
        "backup_scratch_before_restore_20261111T143000",
    ]


def test_rejects_a_file_that_isnt_a_dump(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not a dump")
    with pytest.raises(RestoreError, match="Couldn't read"):
        restore(path)


def test_main_backs_up_and_restores(scratch: Engine) -> None:
    assert main(["backup"]) == 0
    (dump,) = backups.BACKUPS_DIR.glob("db_backup_*.dump")
    add_note(scratch, "changed")
    assert main(["restore", str(dump), "--force"]) == 0
    assert notes(scratch) == ["original"]


def test_main_reports_a_missing_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)
    assert main(["restore", str(tmp_path / "missing.dump")]) == 1
    assert "missing.dump" in caplog.text


@pytest.mark.parametrize(
    ("argv", "restore_hint"),
    [
        pytest.param(["backup"], False, id="backup"),
        pytest.param(["restore", "backups/any.dump"], True, id="restore"),
    ],
)
def test_main_exits_quietly_when_interrupted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    argv: list[str],
    restore_hint: bool,
) -> None:
    def interrupt(*args: object, **kwargs: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(backups, argv[0], interrupt)
    caplog.set_level(logging.ERROR)
    assert main(argv) == 130
    assert "Interrupted" in caplog.text
    # Only a restore can leave the original under its set-aside name.
    assert ("_before_restore_" in caplog.text) is restore_hint
