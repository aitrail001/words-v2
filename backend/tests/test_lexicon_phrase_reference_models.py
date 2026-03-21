import uuid

from sqlalchemy import UniqueConstraint

from app.models.phrase_entry import PhraseEntry
from app.models.reference_entry import ReferenceEntry
from app.models.reference_localization import ReferenceLocalization
from app.models.schema_names import LEXICON_SCHEMA


class TestPhraseEntryModel:
    def test_defaults_and_fields(self) -> None:
        entry = PhraseEntry(
            phrase_text="take off",
            normalized_form="take off",
            phrase_kind="phrasal_verb",
        )
        assert entry.phrase_text == "take off"
        assert entry.normalized_form == "take off"
        assert entry.phrase_kind == "phrasal_verb"
        assert entry.language == "en"
        assert entry.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in PhraseEntry.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert PhraseEntry.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_phrase_entry_normalized_language"
            and {column.name for column in constraint.columns} == {"normalized_form", "language"}
            for constraint in constraints
        )


class TestReferenceEntryModel:
    def test_defaults_and_fields(self) -> None:
        entry = ReferenceEntry(
            reference_type="country",
            display_form="Australia",
            normalized_form="australia",
            translation_mode="localized",
            brief_description="A country in the Southern Hemisphere.",
            pronunciation="/ɔˈstreɪliə/",
        )
        assert entry.reference_type == "country"
        assert entry.display_form == "Australia"
        assert entry.normalized_form == "australia"
        assert entry.translation_mode == "localized"
        assert entry.language == "en"
        assert entry.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in ReferenceEntry.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert ReferenceEntry.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_reference_entry_normalized_language"
            and {column.name for column in constraint.columns} == {"normalized_form", "language"}
            for constraint in constraints
        )


class TestReferenceLocalizationModel:
    def test_defaults_and_relationship_keys(self) -> None:
        localization = ReferenceLocalization(
            reference_entry_id=uuid.uuid4(),
            locale="es",
            display_form="Australia",
        )
        assert localization.locale == "es"
        assert localization.display_form == "Australia"
        assert localization.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in ReferenceLocalization.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert ReferenceLocalization.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_reference_localization_entry_locale"
            and {column.name for column in constraint.columns} == {"reference_entry_id", "locale"}
            for constraint in constraints
        )
