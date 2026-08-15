"""Align the report vocabulary with the product's wording.

Three enum values were named from the schema's point of view rather than the
reporter's. `ALTER TYPE ... RENAME VALUE` rewrites the label in the catalogue
without touching a single row — the on-disk representation of an enum is its
ordinal, not its text.

None of the renamed labels appear in a constraint or index predicate:
`ck_reports_terminal_requires_resolution` names 'resolved' and 'dismissed',
`ck_reports_other_requires_comment` names 'other', and
`uq_reports_job_session_open` names 'open'. All four are unchanged, so nothing
here needs the constraints dropped and rebuilt.

Revision ID: 0004_report_vocabulary
Revises: 0003_search
Created: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_report_vocabulary"
down_revision: str | None = "0003_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (type, old label, new label)
RENAMES: tuple[tuple[str, str, str], ...] = (
    # "spam" describes one specific abuse; the queue also receives scams,
    # ghost listings and fee-charging "employers". "suspicious" is the
    # category a reporter actually recognises.
    ("report_reason", "spam", "suspicious"),
    ("report_reason", "wrong_information", "incorrect_information"),
    # The workflow state is "under review", and the label a moderator sees
    # should be the label the database stores.
    ("report_status", "in_review", "under_review"),
)


def upgrade() -> None:
    for type_name, old, new in RENAMES:
        op.execute(f"ALTER TYPE {type_name} RENAME VALUE '{old}' TO '{new}'")


def downgrade() -> None:
    for type_name, old, new in reversed(RENAMES):
        op.execute(f"ALTER TYPE {type_name} RENAME VALUE '{new}' TO '{old}'")
