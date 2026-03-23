import uuid

from app.models.search_history import SearchHistory
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.user_preference import UserPreference


class TestLearnerEntryStatusModel:
    def test_defaults(self):
        model = LearnerEntryStatus(
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
        )

        assert model.status == "undecided"

    def test_unique_constraint_fields(self):
        constraint = next(
            constraint
            for constraint in LearnerEntryStatus.__table__.constraints
            if constraint.name == "uq_learner_entry_status_user_entry"
        )

        assert {column.name for column in constraint.columns} == {
            "user_id",
            "entry_type",
            "entry_id",
        }

    def test_status_check_constraint_exists(self):
        check_names = {
            constraint.name
            for constraint in LearnerEntryStatus.__table__.constraints
            if getattr(constraint, "name", None)
        }

        assert "ck_learner_entry_status_value" in check_names


class TestUserPreferenceModel:
    def test_defaults(self):
        model = UserPreference(user_id=uuid.uuid4())

        assert model.accent_preference == "us"
        assert model.translation_locale == "zh-Hans"
        assert model.knowledge_view_preference == "cards"

    def test_unique_constraint_fields(self):
        constraint = next(
            constraint
            for constraint in UserPreference.__table__.constraints
            if constraint.name == "uq_user_preferences_user"
        )

        assert {column.name for column in constraint.columns} == {"user_id"}


class TestSearchHistoryModel:
    def test_defaults(self):
        model = SearchHistory(
            user_id=uuid.uuid4(),
            query="bank",
        )

        assert model.entry_type is None
        assert model.entry_id is None

    def test_unique_constraint_fields(self):
        constraint = next(
            constraint
            for constraint in SearchHistory.__table__.constraints
            if constraint.name == "uq_search_history_user_query"
        )

        assert {column.name for column in constraint.columns} == {"user_id", "query"}
