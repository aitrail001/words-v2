"""Collapse lexicon voice storage policies to global defaults

Revision ID: 033
Revises: 032
Create Date: 2026-03-29
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_POLICY_KEYS = {
    "word": "word_default",
    "definition": "definition_default",
    "example": "example_default",
}


def upgrade() -> None:
    connection = op.get_bind()

    for content_scope, policy_key in _DEFAULT_POLICY_KEYS.items():
        root_row = connection.execute(
            sa.text(
                """
                select
                  p.primary_storage_root_id as primary_storage_root_id,
                  p.fallback_storage_root_id as fallback_storage_root_id
                from lexicon.lexicon_voice_assets a
                join lexicon.lexicon_voice_storage_policies p on p.id = a.storage_policy_id
                where a.content_scope = :content_scope
                group by p.primary_storage_root_id, p.fallback_storage_root_id
                order by count(*) desc
                limit 1
                """
            ),
            {"content_scope": content_scope},
        ).mappings().first()

        if root_row is None:
            root_row = connection.execute(
                sa.text(
                    """
                    select
                      primary_storage_root_id as primary_storage_root_id,
                      fallback_storage_root_id as fallback_storage_root_id
                    from lexicon.lexicon_voice_storage_policies
                    where content_scope = :content_scope
                    order by created_at asc
                    limit 1
                    """
                ),
                {"content_scope": content_scope},
            ).mappings().first()

        if root_row is None:
            continue

        existing_policy = connection.execute(
            sa.text(
                """
                select id
                from lexicon.lexicon_voice_storage_policies
                where policy_key = :policy_key
                """
            ),
            {"policy_key": policy_key},
        ).mappings().first()

        if existing_policy is None:
            policy_id = uuid.uuid4()
            connection.execute(
                sa.text(
                    """
                    insert into lexicon.lexicon_voice_storage_policies (
                      id,
                      policy_key,
                      source_reference,
                      content_scope,
                      provider,
                      family,
                      locale,
                      primary_storage_root_id,
                      fallback_storage_root_id
                    ) values (
                      :id,
                      :policy_key,
                      'global',
                      :content_scope,
                      'default',
                      'default',
                      'all',
                      :primary_storage_root_id,
                      :fallback_storage_root_id
                    )
                    """
                ),
                {
                    "id": policy_id,
                    "policy_key": policy_key,
                    "content_scope": content_scope,
                    "primary_storage_root_id": root_row["primary_storage_root_id"],
                    "fallback_storage_root_id": root_row["fallback_storage_root_id"],
                },
            )
        else:
            policy_id = existing_policy["id"]
            connection.execute(
                sa.text(
                    """
                    update lexicon.lexicon_voice_storage_policies
                    set
                      source_reference = 'global',
                      provider = 'default',
                      family = 'default',
                      locale = 'all',
                      primary_storage_root_id = :primary_storage_root_id,
                      fallback_storage_root_id = :fallback_storage_root_id
                    where id = :id
                    """
                ),
                {
                    "id": policy_id,
                    "primary_storage_root_id": root_row["primary_storage_root_id"],
                    "fallback_storage_root_id": root_row["fallback_storage_root_id"],
                },
            )

        connection.execute(
            sa.text(
                """
                update lexicon.lexicon_voice_assets
                set storage_policy_id = :policy_id
                where content_scope = :content_scope
                """
            ),
            {"policy_id": policy_id, "content_scope": content_scope},
        )

    connection.execute(
        sa.text(
            """
            delete from lexicon.lexicon_voice_storage_policies
            where policy_key not in ('word_default', 'definition_default', 'example_default')
            """
        )
    )


def downgrade() -> None:
    raise RuntimeError("033_collapse_voice_storage_policies_to_defaults is not reversible")
