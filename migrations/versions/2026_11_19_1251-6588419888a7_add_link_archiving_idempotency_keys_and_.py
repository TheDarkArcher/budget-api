"""Add link archiving, idempotency keys and triggers

Revision ID: 6588419888a7
Revises: 8df2a8619f65
Create Date: 2026-11-19 12:51:25.019103
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6588419888a7"
down_revision: str | Sequence[str] | None = "8df2a8619f65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        ALTER TABLE transaction_category_item_categories
        ADD COLUMN archived_at timestamptz
    """)

    # A key is stored before its create runs and given the response once the
    # create succeeds, in the same transaction, so a concurrent repeat waits on
    # the unique constraint and then reads the response. Keys sent with no user
    # are unique too.
    op.execute("""
        CREATE TABLE idempotency_keys (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid REFERENCES users (id) ON DELETE CASCADE,
            key text NOT NULL,
            request_hash text NOT NULL,
            response_status integer,
            response_body text,
            response_location text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT idempotency_keys_user_id_key_key
                UNIQUE NULLS NOT DISTINCT (user_id, key),
            CONSTRAINT idempotency_keys_response_complete
                CHECK ((response_status IS NULL) = (response_body IS NULL))
        )
    """)
    op.execute("""
        CREATE INDEX idempotency_keys_created_at_idx
        ON idempotency_keys (created_at)
    """)
    op.execute("""
        CREATE TRIGGER idempotency_keys_set_updated_at
        BEFORE UPDATE ON idempotency_keys
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    # PostgreSQL fires a table's BEFORE triggers in name order, so each
    # <table>_prevent_archived_change runs before the table's other checks and
    # an edit to an archived record is reported as archived first.
    op.execute("""
        CREATE FUNCTION prevent_archived_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.archived_at IS NULL
                AND to_jsonb(NEW) - 'archived_at' - 'updated_at'
                    = to_jsonb(OLD) - 'archived_at' - 'updated_at'
            THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'an archived record can only be unarchived'
                USING ERRCODE = 'integrity_constraint_violation',
                    CONSTRAINT = 'archived_record_immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER transaction_categories_prevent_archived_change
        BEFORE UPDATE ON transaction_categories
        FOR EACH ROW
        WHEN (OLD.archived_at IS NOT NULL)
        EXECUTE FUNCTION prevent_archived_change()
    """)
    op.execute("""
        CREATE TRIGGER item_categories_prevent_archived_change
        BEFORE UPDATE ON item_categories
        FOR EACH ROW
        WHEN (OLD.archived_at IS NOT NULL)
        EXECUTE FUNCTION prevent_archived_change()
    """)
    op.execute("""
        CREATE TRIGGER payees_prevent_archived_change
        BEFORE UPDATE ON payees
        FOR EACH ROW
        WHEN (OLD.archived_at IS NOT NULL)
        EXECUTE FUNCTION prevent_archived_change()
    """)
    op.execute("""
        CREATE TRIGGER items_prevent_archived_change
        BEFORE UPDATE ON items
        FOR EACH ROW
        WHEN (OLD.archived_at IS NOT NULL)
        EXECUTE FUNCTION prevent_archived_change()
    """)
    op.execute("""
        CREATE TRIGGER item_sizes_prevent_archived_change
        BEFORE UPDATE ON item_sizes
        FOR EACH ROW
        WHEN (OLD.archived_at IS NOT NULL)
        EXECUTE FUNCTION prevent_archived_change()
    """)

    # Refuses a change to a column that never changes. The trigger passes the
    # message and the constraint name the API maps.
    op.execute("""
        CREATE FUNCTION refuse_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '%', TG_ARGV[0]
                USING ERRCODE = 'integrity_constraint_violation',
                    CONSTRAINT = TG_ARGV[1];
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER transaction_categories_prevent_type_change
        BEFORE UPDATE OF type ON transaction_categories
        FOR EACH ROW
        WHEN (OLD.type IS DISTINCT FROM NEW.type)
        EXECUTE FUNCTION refuse_change(
            'type cannot be changed', 'transaction_categories_type_immutable'
        )
    """)
    op.execute("""
        CREATE TRIGGER item_sizes_prevent_size_change
        BEFORE UPDATE OF size_value, size_unit ON item_sizes
        FOR EACH ROW
        WHEN (
            OLD.size_value IS DISTINCT FROM NEW.size_value
            OR OLD.size_unit IS DISTINCT FROM NEW.size_unit
        )
        EXECUTE FUNCTION refuse_change(
            'size value and unit cannot be changed', 'item_sizes_size_immutable'
        )
    """)
    op.execute("""
        CREATE TRIGGER item_sizes_prevent_item_id_change
        BEFORE UPDATE OF item_id ON item_sizes
        FOR EACH ROW
        WHEN (OLD.item_id IS DISTINCT FROM NEW.item_id)
        EXECUTE FUNCTION refuse_change(
            'item_id cannot be changed', 'item_sizes_item_id_immutable'
        )
    """)

    # A link can't be added, changed or deleted while either of its categories
    # is archived. A category's own delete still removes its links: by the time
    # the cascade deletes a link, that category's row is already gone. The
    # categories are locked FOR SHARE before they're read, so a concurrent
    # archive is waited for rather than missed; the foreign key's own lock
    # doesn't conflict with an archive. Filtering the lock on archived_at would
    # skip rows whose archive isn't committed yet, so all of them are locked.
    op.execute("""
        CREATE FUNCTION prevent_archived_link_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND (
                NOT EXISTS (
                    SELECT FROM transaction_categories
                    WHERE id = OLD.transaction_category_id
                )
                OR NOT EXISTS (
                    SELECT FROM item_categories WHERE id = OLD.item_category_id
                )
            ) THEN
                RETURN OLD;
            END IF;
            PERFORM FROM transaction_categories
            WHERE id IN (OLD.transaction_category_id, NEW.transaction_category_id)
            FOR SHARE;
            PERFORM FROM item_categories
            WHERE id IN (OLD.item_category_id, NEW.item_category_id)
            FOR SHARE;
            IF EXISTS (
                SELECT FROM transaction_categories
                WHERE id IN (OLD.transaction_category_id, NEW.transaction_category_id)
                    AND archived_at IS NOT NULL
            ) OR EXISTS (
                SELECT FROM item_categories
                WHERE id IN (OLD.item_category_id, NEW.item_category_id)
                    AND archived_at IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'a link cannot change while a category is archived'
                    USING ERRCODE = 'integrity_constraint_violation',
                        CONSTRAINT =
                            'transaction_category_item_categories_category_archived';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER transaction_category_item_categories_prevent_archived_change
        BEFORE INSERT OR UPDATE OR DELETE ON transaction_category_item_categories
        FOR EACH ROW EXECUTE FUNCTION prevent_archived_link_change()
    """)

    # An active transaction category can't be deleted while a link that applies
    # would cascade away. A category a transaction uses is left to the foreign
    # key, which reports the transaction, since unlinking wouldn't help.
    op.execute("""
        CREATE FUNCTION prevent_linked_transaction_category_delete()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM transactions WHERE transaction_category_id = OLD.id
            ) AND EXISTS (
                SELECT FROM transaction_category_item_categories
                    JOIN item_categories
                        ON item_categories.id
                            = transaction_category_item_categories.item_category_id
                WHERE transaction_category_item_categories.transaction_category_id
                        = OLD.id
                    AND transaction_category_item_categories.archived_at IS NULL
                    AND item_categories.archived_at IS NULL
            ) THEN
                RAISE EXCEPTION
                    'transaction category is linked to an active item category'
                    USING ERRCODE = 'restrict_violation',
                        CONSTRAINT = 'transaction_categories_item_category_link';
            END IF;
            RETURN OLD;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER transaction_categories_prevent_linked_delete
        BEFORE DELETE ON transaction_categories
        FOR EACH ROW
        WHEN (OLD.archived_at IS NULL)
        EXECUTE FUNCTION prevent_linked_transaction_category_delete()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER transaction_categories_prevent_linked_delete"
        " ON transaction_categories"
    )
    op.execute("DROP FUNCTION prevent_linked_transaction_category_delete()")
    op.execute(
        "DROP TRIGGER transaction_category_item_categories_prevent_archived_change"
        " ON transaction_category_item_categories"
    )
    op.execute("DROP FUNCTION prevent_archived_link_change()")
    op.execute("DROP TRIGGER item_sizes_prevent_item_id_change ON item_sizes")
    op.execute("DROP TRIGGER item_sizes_prevent_size_change ON item_sizes")
    op.execute(
        "DROP TRIGGER transaction_categories_prevent_type_change"
        " ON transaction_categories"
    )
    op.execute("DROP FUNCTION refuse_change()")
    op.execute("DROP TRIGGER item_sizes_prevent_archived_change ON item_sizes")
    op.execute("DROP TRIGGER items_prevent_archived_change ON items")
    op.execute("DROP TRIGGER payees_prevent_archived_change ON payees")
    op.execute(
        "DROP TRIGGER item_categories_prevent_archived_change ON item_categories"
    )
    op.execute(
        "DROP TRIGGER transaction_categories_prevent_archived_change"
        " ON transaction_categories"
    )
    op.execute("DROP FUNCTION prevent_archived_change()")
    op.execute("DROP TABLE idempotency_keys")
    op.execute(
        "ALTER TABLE transaction_category_item_categories DROP COLUMN archived_at"
    )
