"""Create v1 schema

Revision ID: 8df2a8619f65
Revises:
Create Date: 2026-11-07 01:04:25.919971
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8df2a8619f65"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE TYPE category_type AS ENUM ('income', 'expense')")
    op.execute(
        "CREATE TYPE size_unit AS ENUM ('g', 'kg', 'mL', 'L', 'each', 'unit', 'pack')"
    )

    op.execute("""
        CREATE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
    """)

    op.execute("""
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT users_name_not_blank
                CHECK (btrim(name) != '')
        )
    """)

    op.execute("""
        CREATE TABLE transaction_categories (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            name text NOT NULL,
            type category_type NOT NULL,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT transaction_categories_name_not_blank
                CHECK (btrim(name) != ''),
            CONSTRAINT transaction_categories_user_id_id_key UNIQUE (user_id, id)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX transaction_categories_user_id_name_key
        ON transaction_categories (user_id, lower(name))
    """)

    op.execute("""
        CREATE TABLE item_categories (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            name text NOT NULL,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT item_categories_name_not_blank CHECK (btrim(name) != ''),
            CONSTRAINT item_categories_user_id_id_key UNIQUE (user_id, id)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX item_categories_user_id_name_key
        ON item_categories (user_id, lower(name))
    """)

    op.execute("""
        CREATE TABLE transaction_category_item_categories (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            transaction_category_id uuid NOT NULL
                REFERENCES transaction_categories (id) ON DELETE CASCADE,
            item_category_id uuid NOT NULL
                REFERENCES item_categories (id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT transaction_category_item_categories_pair_key
                UNIQUE (transaction_category_id, item_category_id)
        )
    """)
    op.execute("""
        CREATE INDEX transaction_category_item_categories_item_category_id_idx
        ON transaction_category_item_categories (item_category_id)
    """)

    op.execute("""
        CREATE TABLE payees (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            name text NOT NULL,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT payees_name_not_blank CHECK (btrim(name) != ''),
            CONSTRAINT payees_user_id_id_key UNIQUE (user_id, id)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX payees_user_id_name_key
        ON payees (user_id, lower(name))
    """)

    op.execute("""
        CREATE TABLE tags (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            name text NOT NULL,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT tags_name_not_blank CHECK (btrim(name) != '')
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX tags_user_id_name_key
        ON tags (user_id, lower(name))
    """)

    op.execute("""
        CREATE TABLE items (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            name text NOT NULL,
            item_category_id uuid NOT NULL,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT items_name_not_blank CHECK (btrim(name) != ''),
            CONSTRAINT items_user_id_item_category_id_fkey
                FOREIGN KEY (user_id, item_category_id)
                REFERENCES item_categories (user_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX items_user_id_name_key
        ON items (user_id, lower(name))
    """)
    op.execute("CREATE INDEX items_item_category_id_idx ON items (item_category_id)")

    op.execute("""
        CREATE TABLE item_sizes (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            item_id uuid NOT NULL REFERENCES items (id) ON DELETE CASCADE,
            size_value numeric(12, 2) NOT NULL,
            size_unit size_unit NOT NULL,
            archived_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT item_sizes_size_value_positive CHECK (size_value > 0),
            CONSTRAINT item_sizes_item_id_size_value_size_unit_key
                UNIQUE (item_id, size_value, size_unit)
        )
    """)

    op.execute("""
        CREATE TABLE item_tags (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            item_id uuid NOT NULL REFERENCES items (id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT item_tags_item_id_tag_id_key UNIQUE (item_id, tag_id)
        )
    """)
    op.execute("CREATE INDEX item_tags_tag_id_idx ON item_tags (tag_id)")

    op.execute("""
        CREATE TABLE transactions (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
            occurred_on date NOT NULL,
            transaction_category_id uuid NOT NULL,
            payee_id uuid NOT NULL,
            notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT transactions_user_id_transaction_category_id_fkey
                FOREIGN KEY (user_id, transaction_category_id)
                REFERENCES transaction_categories (user_id, id) ON DELETE RESTRICT,
            CONSTRAINT transactions_user_id_payee_id_fkey
                FOREIGN KEY (user_id, payee_id)
                REFERENCES payees (user_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE INDEX transactions_user_id_occurred_on_idx
        ON transactions (user_id, occurred_on DESC)
    """)
    op.execute("""
        CREATE INDEX transactions_transaction_category_id_idx
        ON transactions (transaction_category_id)
    """)
    op.execute("CREATE INDEX transactions_payee_id_idx ON transactions (payee_id)")

    op.execute("""
        CREATE TABLE transaction_lines (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            transaction_id uuid NOT NULL
                REFERENCES transactions (id) ON DELETE CASCADE,
            item_size_id uuid NOT NULL REFERENCES item_sizes (id) ON DELETE RESTRICT,
            quantity numeric(12, 3) NOT NULL,
            line_total numeric(12, 2) NOT NULL,
            is_discounted boolean NOT NULL DEFAULT false,
            notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT transaction_lines_quantity_positive CHECK (quantity > 0),
            CONSTRAINT transaction_lines_line_total_positive CHECK (line_total > 0)
        )
    """)
    op.execute("""
        CREATE INDEX transaction_lines_transaction_id_idx
        ON transaction_lines (transaction_id)
    """)
    op.execute("""
        CREATE INDEX transaction_lines_item_size_id_idx
        ON transaction_lines (item_size_id)
    """)

    op.execute("""
        CREATE VIEW transaction_totals AS
        SELECT
            transactions.id,
            transactions.user_id,
            transactions.occurred_on,
            transactions.transaction_category_id,
            transactions.payee_id,
            coalesce(sum(transaction_lines.line_total), 0) AS total,
            count(transaction_lines.id) AS line_count
        FROM transactions
            LEFT JOIN transaction_lines
                ON transaction_lines.transaction_id = transactions.id
        GROUP BY transactions.id
    """)

    op.execute("""
        CREATE VIEW items_information AS
        SELECT
            item_sizes.id,
            item_sizes.item_id,
            items.user_id,
            items.name,
            items.item_category_id,
            item_sizes.size_value,
            item_sizes.size_unit,
            items.archived_at AS item_archived_at,
            item_sizes.archived_at AS size_archived_at,
            coalesce(
                array_agg(tags.name ORDER BY lower(tags.name))
                    FILTER (WHERE tags.id IS NOT NULL),
                '{}'::text[]
            ) AS tags
        FROM item_sizes
            JOIN items ON items.id = item_sizes.item_id
            LEFT JOIN item_tags ON item_tags.item_id = items.id
            LEFT JOIN tags
                ON tags.id = item_tags.tag_id AND tags.archived_at IS NULL
        GROUP BY item_sizes.id, items.id
    """)

    op.execute("""
        CREATE TRIGGER users_set_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER transaction_categories_set_updated_at
        BEFORE UPDATE ON transaction_categories
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER item_categories_set_updated_at
        BEFORE UPDATE ON item_categories
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER transaction_category_item_categories_set_updated_at
        BEFORE UPDATE ON transaction_category_item_categories
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER payees_set_updated_at
        BEFORE UPDATE ON payees
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER tags_set_updated_at
        BEFORE UPDATE ON tags
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER items_set_updated_at
        BEFORE UPDATE ON items
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER item_sizes_set_updated_at
        BEFORE UPDATE ON item_sizes
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER item_tags_set_updated_at
        BEFORE UPDATE ON item_tags
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER transactions_set_updated_at
        BEFORE UPDATE ON transactions
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER transaction_lines_set_updated_at
        BEFORE UPDATE ON transaction_lines
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE FUNCTION prevent_user_id_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'user_id cannot be changed'
                USING ERRCODE = 'integrity_constraint_violation',
                    CONSTRAINT = 'user_id_immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER transaction_categories_prevent_user_id_change
        BEFORE UPDATE OF user_id ON transaction_categories
        FOR EACH ROW
        WHEN (OLD.user_id IS DISTINCT FROM NEW.user_id)
        EXECUTE FUNCTION prevent_user_id_change()
    """)
    op.execute("""
        CREATE TRIGGER item_categories_prevent_user_id_change
        BEFORE UPDATE OF user_id ON item_categories
        FOR EACH ROW
        WHEN (OLD.user_id IS DISTINCT FROM NEW.user_id)
        EXECUTE FUNCTION prevent_user_id_change()
    """)
    op.execute("""
        CREATE TRIGGER payees_prevent_user_id_change
        BEFORE UPDATE OF user_id ON payees
        FOR EACH ROW
        WHEN (OLD.user_id IS DISTINCT FROM NEW.user_id)
        EXECUTE FUNCTION prevent_user_id_change()
    """)
    op.execute("""
        CREATE TRIGGER tags_prevent_user_id_change
        BEFORE UPDATE OF user_id ON tags
        FOR EACH ROW
        WHEN (OLD.user_id IS DISTINCT FROM NEW.user_id)
        EXECUTE FUNCTION prevent_user_id_change()
    """)
    op.execute("""
        CREATE TRIGGER items_prevent_user_id_change
        BEFORE UPDATE OF user_id ON items
        FOR EACH ROW
        WHEN (OLD.user_id IS DISTINCT FROM NEW.user_id)
        EXECUTE FUNCTION prevent_user_id_change()
    """)
    op.execute("""
        CREATE TRIGGER transactions_prevent_user_id_change
        BEFORE UPDATE OF user_id ON transactions
        FOR EACH ROW
        WHEN (OLD.user_id IS DISTINCT FROM NEW.user_id)
        EXECUTE FUNCTION prevent_user_id_change()
    """)

    # User matching for links between tables without a user_id; the rest use
    # composite foreign keys. Each check only rejects a row that exists under
    # another user, leaving a missing row to the foreign key. They report
    # foreign_key_violation, as a bad reference, under a name the API can map.
    op.execute("""
        CREATE FUNCTION check_transaction_category_item_category_user()
        RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT FROM transaction_categories
                    JOIN item_categories
                        ON item_categories.id = NEW.item_category_id
                WHERE transaction_categories.id = NEW.transaction_category_id
                    AND transaction_categories.user_id != item_categories.user_id
            ) THEN
                RAISE EXCEPTION 'linked categories belong to different users'
                    USING ERRCODE = 'foreign_key_violation',
                        CONSTRAINT = 'transaction_category_item_categories_same_user';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER transaction_category_item_categories_check_user
        BEFORE INSERT OR UPDATE OF transaction_category_id, item_category_id
        ON transaction_category_item_categories
        FOR EACH ROW
        EXECUTE FUNCTION check_transaction_category_item_category_user()
    """)

    op.execute("""
        CREATE FUNCTION check_item_tag_user() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT FROM items
                    JOIN tags ON tags.id = NEW.tag_id
                WHERE items.id = NEW.item_id AND items.user_id != tags.user_id
            ) THEN
                RAISE EXCEPTION 'item and tag belong to different users'
                    USING ERRCODE = 'foreign_key_violation',
                        CONSTRAINT = 'item_tags_same_user';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER item_tags_check_user
        BEFORE INSERT OR UPDATE OF item_id, tag_id ON item_tags
        FOR EACH ROW EXECUTE FUNCTION check_item_tag_user()
    """)

    op.execute("""
        CREATE FUNCTION check_transaction_line_user() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (
                SELECT FROM transactions
                    JOIN item_sizes ON item_sizes.id = NEW.item_size_id
                    JOIN items ON items.id = item_sizes.item_id
                WHERE transactions.id = NEW.transaction_id
                    AND transactions.user_id != items.user_id
            ) THEN
                RAISE EXCEPTION 'transaction and item belong to different users'
                    USING ERRCODE = 'foreign_key_violation',
                        CONSTRAINT = 'transaction_lines_same_user';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER transaction_lines_check_user
        BEFORE INSERT OR UPDATE OF transaction_id, item_size_id ON transaction_lines
        FOR EACH ROW EXECUTE FUNCTION check_transaction_line_user()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW items_information")
    op.execute("DROP VIEW transaction_totals")
    op.execute("DROP TABLE transaction_lines")
    op.execute("DROP TABLE transactions")
    op.execute("DROP TABLE item_tags")
    op.execute("DROP TABLE item_sizes")
    op.execute("DROP TABLE items")
    op.execute("DROP TABLE tags")
    op.execute("DROP TABLE payees")
    op.execute("DROP TABLE transaction_category_item_categories")
    op.execute("DROP TABLE item_categories")
    op.execute("DROP TABLE transaction_categories")
    op.execute("DROP TABLE users")
    op.execute("DROP FUNCTION check_transaction_line_user()")
    op.execute("DROP FUNCTION check_item_tag_user()")
    op.execute("DROP FUNCTION check_transaction_category_item_category_user()")
    op.execute("DROP FUNCTION prevent_user_id_change()")
    op.execute("DROP FUNCTION set_updated_at()")
    op.execute("DROP TYPE size_unit")
    op.execute("DROP TYPE category_type")
