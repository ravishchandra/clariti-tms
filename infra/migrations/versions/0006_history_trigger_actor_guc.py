"""Per-actor identity in translation_history via Postgres GUCs.

F4 — replaces the hardcoded ``change_source = 'system'`` in the
``record_translation_history`` trigger function with values read from
session-level GUCs:

* ``current_setting('app.changed_by', true)`` — UUID of the acting user
  (NULL when unset, e.g. system-driven changes).
* ``current_setting('app.change_source', true)`` — free-form caller tag
  (``'api'``, ``'cli'``, falls back to ``'system'`` when unset).

The second argument ``true`` means "return NULL if the setting is not
defined" — without it, ``current_setting`` raises. Both values are read
as text and cast: ``change_source`` stays text, ``changed_by`` is cast
to UUID after a NULLIF on the empty string (an empty GUC reads as ``''``
on some Postgres versions, which would fail a UUID cast).

System paths (MT worker, ingestion, publication, CLI) don't set these
GUCs — their sessions are minted via ``AsyncSessionLocal()`` directly,
not the ``get_db`` request dependency that installs them — so they
correctly fall back to ``(NULL, 'system')``.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_FUNCTION = """
CREATE OR REPLACE FUNCTION record_translation_history()
RETURNS TRIGGER AS $$
DECLARE
  v_changed_by uuid;
  v_change_source text;
BEGIN
  -- Read session-level GUCs set by the application. The `true` second
  -- argument makes current_setting return NULL when the GUC is unset
  -- instead of raising "unrecognized configuration parameter".
  v_changed_by := NULLIF(current_setting('app.changed_by', true), '')::uuid;
  v_change_source := COALESCE(
    NULLIF(current_setting('app.change_source', true), ''),
    'system'
  );

  INSERT INTO translation_history (
    translation_id, prev_value, new_value,
    prev_status, new_status,
    changed_by, change_source,
    changed_at
  ) VALUES (
    NEW.id, OLD.value, NEW.value,
    OLD.status, NEW.status,
    v_changed_by, v_change_source,
    now()
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


_OLD_FUNCTION = """
CREATE OR REPLACE FUNCTION record_translation_history()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO translation_history (
    translation_id, prev_value, new_value,
    prev_status, new_status, change_source, changed_at
  ) VALUES (
    NEW.id, OLD.value, NEW.value,
    OLD.status, NEW.status, 'system', now()
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_NEW_FUNCTION)


def downgrade() -> None:
    op.execute(_OLD_FUNCTION)
