"""Back up the database to a file, or restore it from one.

Both run PostgreSQL's own tools inside the ``db`` container, as the
container's ``POSTGRES_USER``, so they always match the server's version and
need no connection details here. Dumps are streamed to and from the
git-ignored ``backups/`` folder on the host and never stored in the container.

Usage:
    uv run poe backup
    uv run poe restore backups/db_backup_<timestamp>.dump [-f | --force]

Stop the app before restoring: a restore refuses to replace a database that
anything is still connected to.
"""

import argparse
import logging
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = ROOT / "backups"

# Runs a command in the Compose `db` service's container, reading stdin.
COMPOSE_DB = ("docker", "compose", "exec", "-T", "db")

# The database psql and pg_restore connect to when working on another one.
MAINTENANCE_DATABASE = "postgres"

# PostgreSQL silently cuts longer database names short.
MAX_NAME_LENGTH = 63

DUMP_DATABASE_NAME = re.compile(r"^;[ \t]+dbname: (.+)$", re.MULTILINE)

# Counts the schema objects and large objects in the current database, where
# its data could be. Zero means it's empty: nothing has been created in it,
# so it can be dropped, and recreated empty if a restore fails. Tables,
# views, sequences and indexes are all in pg_class.
COUNT_NON_EMPTY_SQL = """
WITH public_schema AS (SELECT oid FROM pg_namespace WHERE nspname = 'public')
SELECT
    (SELECT count(*) FROM pg_namespace
        WHERE nspname !~ '^pg_' AND nspname NOT IN ('information_schema', 'public'))
    + (SELECT count(*) FROM pg_class
        WHERE relnamespace IN (SELECT oid FROM public_schema))
    + (SELECT count(*) FROM pg_type
        WHERE typnamespace IN (SELECT oid FROM public_schema))
    + (SELECT count(*) FROM pg_proc
        WHERE pronamespace IN (SELECT oid FROM public_schema))
    + (SELECT count(*) FROM pg_largeobject_metadata);
"""


class DatabaseCommandError(Exception):
    """Raised when a command in the database container fails."""


class RestoreError(Exception):
    """Raised when a restore can't go ahead or fails.

    The message says whether anything was changed, and where the original
    data is if it couldn't be put back.
    """


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _run(
    script: str,
    *args: str,
    stdin: BinaryIO | None = None,
    input_text: str | None = None,
    stdout: BinaryIO | None = None,
) -> str:
    # The script runs in the container's shell, so it can read the
    # container's POSTGRES_USER and POSTGRES_DB. The command comes from this
    # module's constants; values, including names read from a dump, reach the
    # script only as positional arguments ($1, $2), never as part of its text,
    # which is why the call is safe (S603). It runs from the project root,
    # where `docker compose` finds compose.yaml.
    try:
        result = subprocess.run(  # noqa: S603
            [*COMPOSE_DB, "sh", "-c", script, "sh", *args],
            cwd=ROOT,
            stdin=stdin,
            input=None if input_text is None else input_text.encode(),
            stdout=subprocess.PIPE if stdout is None else stdout,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DatabaseCommandError(
            f"Couldn't run {COMPOSE_DB[0]}; is it installed and on PATH?"
        ) from exc
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip() or "no error output"
        raise DatabaseCommandError(f"{message} (exit status {result.returncode})")
    return "" if stdout is not None else result.stdout.decode(errors="replace")


def _psql(sql: str, **variables: str) -> str:
    # Values are passed as psql variables and quoted by psql itself, as
    # :'name' for a literal or :"name" for an identifier.
    options = [f'-v {name}="${index}"' for index, name in enumerate(variables, 1)]
    script = (
        'psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
        f"-d {MAINTENANCE_DATABASE} {' '.join(options)}"
    )
    return _run(script, *variables.values(), input_text=sql).strip()


def backup() -> Path:
    """Dump the container's database to a new timestamped file in ``backups/``.

    The database is the container's ``POSTGRES_DB``, the folder is created if
    needed, and the file is readable only by its owner.

    Returns:
        The path of the new dump.

    Raises:
        FileExistsError: If a dump with the same timestamp already exists.
        DatabaseCommandError: If ``pg_dump`` fails. As after any failure or
            interruption, no file is left behind.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUPS_DIR / f"db_backup_{_timestamp()}.dump"
    # PGDATABASE is never read as a connection string, whatever the name
    # contains.
    script = 'PGDATABASE="$POSTGRES_DB" pg_dump -Fc -U "$POSTGRES_USER"'
    path.touch(mode=0o600, exist_ok=False)
    try:
        with path.open("wb") as dump:
            _run(script, stdout=dump)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _read_database_name(dump: BinaryIO, path: Path) -> str:
    # Reads from the dump's current position; callers that reuse the file
    # afterwards rewind it first.
    try:
        listing = _run("pg_restore -l", stdin=dump)
    except DatabaseCommandError as exc:
        raise RestoreError(f"Couldn't read {path} as a dump: {exc}") from exc
    match = DUMP_DATABASE_NAME.search(listing)
    if match is None:
        raise RestoreError(f"{path} doesn't say which database it's from")
    return match.group(1)


def _is_empty(database: str) -> bool:
    # Empty means nothing counted by COUNT_NON_EMPTY_SQL. If the database
    # can't be checked, for example because it can't be connected to, it's
    # treated as not empty, so it's kept rather than dropped, and the reason
    # is logged.
    script = 'PGDATABASE="$1" psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$POSTGRES_USER"'
    try:
        count = _run(script, database, input_text=COUNT_NON_EMPTY_SQL)
    except (DatabaseCommandError, OSError) as exc:
        logger.warning('Couldn\'t check whether "%s" is empty: %s', database, exc)
        return False
    return count.strip() == "0"


def _undo_and_describe(
    path: Path,
    database: str,
    cause: str,
    *,
    aside: str | None = None,
    recreate_empty: bool = False,
) -> RestoreError:
    # Drops whatever the failed restore created and puts back what was
    # there: the set-aside database, or a new empty one in place of the empty
    # database that was dropped. Then returns the error describing what
    # happened, for the caller to raise or report. Anything still connected
    # to the database is the failed restore itself, so the drop disconnects
    # it. The one exception is a database of the same name created by someone
    # else between the existence check and the restore, which would be
    # dropped too; on a single-user development machine that race isn't worth
    # guarding against.
    try:
        _psql('DROP DATABASE IF EXISTS :"database" WITH (FORCE);', database=database)
        if aside is not None:
            _psql(
                'ALTER DATABASE :"aside" RENAME TO :"database";',
                database=database,
                aside=aside,
            )
        elif recreate_empty:
            _psql('CREATE DATABASE :"database";', database=database)
    except (DatabaseCommandError, OSError) as exc:
        if aside is not None:
            where = (
                f'The original data is safe in the database "{aside}". Once the '
                f'cause is fixed, drop any partly restored "{database}", then '
                f'rename "{aside}" back to "{database}".'
            )
        elif recreate_empty:
            where = (
                f'"{database}" was empty, so no data was lost, but it may now be '
                "missing or partly restored; once the cause is fixed, drop it if "
                "it exists and create it again."
            )
        else:
            where = (
                "There was no database before, so no data was lost, but a "
                f'partly restored "{database}" may be left to drop.'
            )
        return RestoreError(
            f"Restoring {path} failed ({cause}), and so did undoing it ({exc}). {where}"
        )
    return RestoreError(f"Restoring {path} failed; nothing was changed: {cause}")


def _check_replaceable(database: str, aside: str, *, force: bool) -> bool:
    # Refuses, by raising RestoreError, if the existing database can't be
    # replaced; otherwise returns whether it's empty. Only client connections
    # count; background workers don't block the rename or drop. They're
    # checked first, so a database in use is refused before anything else; a
    # client connecting after the check makes the drop or rename refuse.
    connections = _psql(
        "SELECT count(*) FROM pg_stat_activity"
        " WHERE datname = :'database' AND backend_type = 'client backend';",
        database=database,
    )
    if connections != "0":
        raise RestoreError(
            f'The database "{database}" is in use; stop the app first, '
            "e.g. `docker compose stop api`, then try again"
        )
    if _is_empty(database):
        return True
    if not force:
        raise RestoreError(
            f"The database \"{database}\" isn't empty, or couldn't be checked; "
            "restore with --force to replace it"
        )
    # The limit is in bytes, and longer names are silently cut short.
    if len(aside.encode()) > MAX_NAME_LENGTH:
        raise RestoreError(
            f'The database name "{database}" is too long to set aside safely '
            "while restoring; nothing was changed"
        )
    return False


def _make_room(database: str, aside: str, *, empty: bool) -> None:
    # An empty database has nothing to keep, so it's dropped; a plain DROP
    # refuses if anything has connected since the check. Any other is
    # renamed aside.
    try:
        if empty:
            _psql('DROP DATABASE :"database";', database=database)
        else:
            _psql(
                'ALTER DATABASE :"database" RENAME TO :"aside";',
                database=database,
                aside=aside,
            )
    except (DatabaseCommandError, OSError) as exc:
        action = "replace the empty" if empty else "set aside the"
        raise RestoreError(
            f'Couldn\'t {action} database "{database}"; nothing was changed: {exc}'
        ) from exc


def restore(path: Path, force: bool = False) -> str:
    """Restore a dump into the database it was taken from.

    A database of that name that doesn't exist or is empty, with no schema
    objects or large objects in it, is replaced without asking: an empty
    one is simply dropped, and recreated empty if the restore fails. One
    that isn't empty is only replaced with ``force``; it's renamed aside
    to a timestamped name rather than dropped, and put back if the restore
    fails or is interrupted. One that anything is connected to is never
    replaced.

    Args:
        path: The dump file to restore.
        force: Replace the database even if it isn't empty.

    Returns:
        The name of the restored database.

    Raises:
        RestoreError: If the restore can't go ahead, or fails. The message
            says where the original data is if it couldn't be put back.
        DatabaseCommandError: If checking the existing database fails, before
            anything has changed.
        OSError: If a command can't be started for a reason other than a
            missing executable, such as missing permissions.
        KeyboardInterrupt: If interrupted with Ctrl-C. If that happens while
            ``pg_restore`` runs, the original is put back and what happened
            is logged first. At any other moment the original may be left
            under its set-aside name, or, if it was empty, the database may
            be missing.
    """
    # Opened once, before anything changes: an unreadable dump changes
    # nothing, and the name checked is read from the file that's restored.
    try:
        dump = path.open("rb")
    except OSError as exc:
        raise RestoreError(f"Couldn't open {path}; nothing was changed: {exc}") from exc

    with dump:
        database = _read_database_name(dump, path)
        dump.seek(0)
        aside = f"{database}_before_restore_{_timestamp()}"
        exists = bool(
            _psql(
                "SELECT 1 FROM pg_database WHERE datname = :'database';",
                database=database,
            )
        )
        empty = False
        if exists:
            empty = _check_replaceable(database, aside, force=force)
            _make_room(database, aside, empty=empty)

        original = aside if exists and not empty else None
        try:
            _run(
                'pg_restore --create --exit-on-error -U "$POSTGRES_USER" '
                f"-d {MAINTENANCE_DATABASE}",
                stdin=dump,
            )
        except (DatabaseCommandError, OSError) as exc:
            raise _undo_and_describe(
                path, database, str(exc), aside=original, recreate_empty=empty
            ) from exc
        except KeyboardInterrupt:
            # Interrupted with Ctrl-C: put things back, say what happened, then
            # stop.
            outcome = _undo_and_describe(
                path, database, "interrupted", aside=original, recreate_empty=empty
            )
            logger.error("%s", outcome)
            raise

    if original is not None:
        try:
            _psql('DROP DATABASE :"aside";', aside=aside)
        except (DatabaseCommandError, OSError) as exc:
            logger.warning(
                'Restored "%s", but couldn\'t drop the set-aside copy "%s": %s',
                database,
                aside,
                exc,
            )
    return database


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``backup`` or ``restore`` command.

    Args:
        argv: The command-line arguments, ``sys.argv[1:]`` by default.

    Returns:
        The exit status: 0 on success, 1 if the command failed, or 130 if it
        was interrupted with Ctrl-C.
    """
    parser = argparse.ArgumentParser(description="Back up or restore the database.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup", help="dump the database to backups/")
    restore_parser = commands.add_parser("restore", help="restore a dump")
    restore_parser.add_argument("file", type=Path, help="the dump to restore")
    restore_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="replace the database even if it isn't empty",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "backup":
            path = backup()
            logger.info("Backed up the database to %s", path)
        else:
            database = restore(args.file, force=args.force)
            logger.info('Restored "%s" from %s', database, args.file)
    except (DatabaseCommandError, RestoreError, OSError) as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        # Anything undone has already been reported; skip the traceback.
        if args.command == "restore":
            logger.error(
                "Interrupted; if the restore had started, check for a database "
                "named <name>_before_restore_<timestamp> holding the original "
                "data, or, if the database was empty and is now missing, "
                "recreate it with `docker compose exec db createdb -U <user> "
                "<name>` (see the README's Backups section)"
            )
        else:
            logger.error("Interrupted")
        return 130
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(main())
