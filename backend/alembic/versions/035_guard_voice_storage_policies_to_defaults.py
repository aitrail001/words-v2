"""Guard voice storage policies to the default set

Revision ID: 035
Revises: 034
Create Date: 2026-03-29
"""

from typing import Sequence, Union

from alembic import op


revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_lexicon_voice_storage_policies_allowed_keys",
        "lexicon_voice_storage_policies",
        "policy_key IN ('word_default', 'definition_default', 'example_default')",
        schema="lexicon",
    )
    op.create_check_constraint(
        "ck_lexicon_voice_storage_policies_key_matches_scope",
        "lexicon_voice_storage_policies",
        "(policy_key = 'word_default' AND content_scope = 'word') OR "
        "(policy_key = 'definition_default' AND content_scope = 'definition') OR "
        "(policy_key = 'example_default' AND content_scope = 'example')",
        schema="lexicon",
    )
    op.create_check_constraint(
        "ck_lexicon_voice_storage_policies_global_source",
        "lexicon_voice_storage_policies",
        "source_reference = 'global'",
        schema="lexicon",
    )
    op.create_check_constraint(
        "ck_lexicon_voice_storage_policies_default_provider",
        "lexicon_voice_storage_policies",
        "provider = 'default'",
        schema="lexicon",
    )
    op.create_check_constraint(
        "ck_lexicon_voice_storage_policies_default_family",
        "lexicon_voice_storage_policies",
        "family = 'default'",
        schema="lexicon",
    )
    op.create_check_constraint(
        "ck_lexicon_voice_storage_policies_all_locale",
        "lexicon_voice_storage_policies",
        "locale = 'all'",
        schema="lexicon",
    )


def downgrade() -> None:
    op.drop_constraint("ck_lexicon_voice_storage_policies_all_locale", "lexicon_voice_storage_policies", schema="lexicon", type_="check")
    op.drop_constraint("ck_lexicon_voice_storage_policies_default_family", "lexicon_voice_storage_policies", schema="lexicon", type_="check")
    op.drop_constraint("ck_lexicon_voice_storage_policies_default_provider", "lexicon_voice_storage_policies", schema="lexicon", type_="check")
    op.drop_constraint("ck_lexicon_voice_storage_policies_global_source", "lexicon_voice_storage_policies", schema="lexicon", type_="check")
    op.drop_constraint("ck_lexicon_voice_storage_policies_key_matches_scope", "lexicon_voice_storage_policies", schema="lexicon", type_="check")
    op.drop_constraint("ck_lexicon_voice_storage_policies_allowed_keys", "lexicon_voice_storage_policies", schema="lexicon", type_="check")
