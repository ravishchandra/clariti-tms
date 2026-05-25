"""Backfill ``locale_configs.is_activated`` and ``is_bootstrapped`` from
existing translation state.

Migration 0009 added these two columns with ``server_default='false'``,
which is the right default for net-new locale_configs but grandfathers
every pre-existing row into the wrong state. A project whose translations
were already approved or published before 0009 ran ends up looking
"registered, not activated" in Settings → Locales — even though hundreds
of translation rows exist downstream.

This migration derives the truth from the ``translations`` table:

- ``is_activated = true`` when *any* translation row exists for the
  ``(project_id, locale)`` pair. Existence of a row means fan-out happened
  at some point (either via the new ``?fan_out=true`` endpoint or via the
  pre-0009 ingest path that fanned out at key creation time).

- ``is_bootstrapped = true`` when at least one translation reached
  ``approved`` or ``published`` for that pair. Per docs/06, those statuses
  imply human or post-bootstrap MT sign-off — both are downstream of the
  50-string native-speaker pass.

Idempotent: re-running has no effect on rows that already have the right
values; the UPDATE statements only flip ``false → true`` where the EXISTS
condition holds.

Online-safe: read-mostly with a small write set; no schema changes.

Downgrade is a no-op — we have no way to tell which rows were ``true`` by
operator action vs. set by this backfill, so reverting would damage
operator-set state. Documented inline below.
"""

from __future__ import annotations

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # is_activated: any translation row exists for (project_id, locale).
    # The join chain translations → keys → repositories → locale_configs.project_id
    # mirrors the read path the UI uses for the same locale state.
    op.execute(
        """
        UPDATE locale_configs lc
        SET is_activated = true
        WHERE is_activated = false
          AND EXISTS (
            SELECT 1
              FROM translations t
              JOIN keys k ON k.id = t.key_id
              JOIN repositories r ON r.id = k.repository_id
             WHERE r.project_id = lc.project_id
               AND t.locale = lc.locale
          )
        """
    )

    # is_bootstrapped: at least one translation reached approved or published.
    # Those statuses are the post-bootstrap states per the docs/06 state
    # machine; their existence implies the locale was usable in the original
    # (pre-two-button) flow.
    op.execute(
        """
        UPDATE locale_configs lc
        SET is_bootstrapped = true
        WHERE is_bootstrapped = false
          AND EXISTS (
            SELECT 1
              FROM translations t
              JOIN keys k ON k.id = t.key_id
              JOIN repositories r ON r.id = k.repository_id
             WHERE r.project_id = lc.project_id
               AND t.locale = lc.locale
               AND t.status IN ('approved', 'published')
          )
        """
    )


def downgrade() -> None:
    # No-op by design. After this migration runs, ``is_activated`` and
    # ``is_bootstrapped`` may be ``true`` either because of operator action
    # or because of this backfill — we can't distinguish the two cases, and
    # blindly setting them back to false would damage operator-set state.
    # The 0009 downgrade is the right escape hatch if a full rollback is
    # required (it drops both columns entirely).
    pass
