import unittest
from pathlib import Path

from tools.lexicon.config import LexiconSettings


class LexiconSettingsTests(unittest.TestCase):
    def test_settings_default_output_root_uses_repo_data_dir(self) -> None:
        settings = LexiconSettings.from_env({})

        self.assertEqual(settings.output_root, Path("data/lexicon"))
        self.assertEqual(settings.llm_timeout_seconds, 60)
        self.assertEqual(settings.llm_reasoning_effort, "none")

    def test_settings_reads_llm_values_from_env(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-5.4",
                "LEXICON_LLM_API_KEY": "secret-key",
            }
        )

        self.assertEqual(settings.llm_base_url, "https://api.example.test/v1")
        self.assertEqual(settings.llm_model, "gpt-5.4")
        self.assertEqual(settings.llm_api_key, "secret-key")

    def test_settings_supports_legacy_provider_env_as_endpoint_alias(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_PROVIDER": "https://legacy.example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-5.4",
                "LEXICON_LLM_API_KEY": "secret-key",
            }
        )

        self.assertEqual(settings.llm_base_url, "https://legacy.example.test/v1")
        self.assertEqual(settings.llm_provider, "https://legacy.example.test/v1")

    def test_settings_reads_optional_llm_transport(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.example.test",
                "LEXICON_LLM_MODEL": "gpt-5.1",
                "LEXICON_LLM_API_KEY": "secret-key",
                "LEXICON_LLM_TRANSPORT": "node",
            }
        )

        self.assertEqual(settings.llm_transport, "node")

    def test_settings_reads_optional_timeout_seconds_minimal_env(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_TIMEOUT_SECONDS": "120",
            }
        )

        self.assertEqual(settings.llm_timeout_seconds, 120)

    def test_settings_reads_optional_timeout_seconds_with_llm_env(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.example.test",
                "LEXICON_LLM_MODEL": "gpt-5.4",
                "LEXICON_LLM_API_KEY": "secret-key",
                "LEXICON_LLM_TIMEOUT_SECONDS": "120",
            }
        )

        self.assertEqual(settings.llm_timeout_seconds, 120)

    def test_settings_rejects_invalid_timeout_seconds_zero(self) -> None:
        with self.assertRaises(ValueError):
            LexiconSettings.from_env({"LEXICON_LLM_TIMEOUT_SECONDS": "0"})

    def test_settings_rejects_invalid_timeout_seconds_non_numeric(self) -> None:
        with self.assertRaises(ValueError):
            LexiconSettings.from_env({"LEXICON_LLM_TIMEOUT_SECONDS": "fast"})

    def test_settings_reads_optional_reasoning_effort(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.example.test",
                "LEXICON_LLM_MODEL": "gpt-5.4",
                "LEXICON_LLM_API_KEY": "secret-key",
                "LEXICON_LLM_REASONING_EFFORT": "low",
            }
        )

        self.assertEqual(settings.llm_reasoning_effort, "low")

    def test_settings_reads_reasoning_effort_none(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.example.test",
                "LEXICON_LLM_MODEL": "gpt-5.4",
                "LEXICON_LLM_API_KEY": "secret-key",
                "LEXICON_LLM_REASONING_EFFORT": "none",
            }
        )

        self.assertEqual(settings.llm_reasoning_effort, "none")

    def test_settings_rejects_invalid_reasoning_effort(self) -> None:
        with self.assertRaises(ValueError):
            LexiconSettings.from_env({"LEXICON_LLM_REASONING_EFFORT": "turbo"})

    def test_settings_reads_core_stage_llm_values_from_env(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://generic.example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-generic",
                "LEXICON_LLM_API_KEY": "generic-key",
                "LEXICON_CORE_LLM_BASE_URL": "https://core.example.test/v1",
                "LEXICON_CORE_LLM_MODEL": "gpt-5.4",
                "LEXICON_CORE_LLM_API_KEY": "core-key",
                "LEXICON_CORE_LLM_TRANSPORT": "node",
                "LEXICON_CORE_LLM_REASONING_EFFORT": "medium",
                "LEXICON_CORE_LLM_TIMEOUT_SECONDS": "180",
            },
            stage="core",
        )

        self.assertEqual(settings.llm_base_url, "https://core.example.test/v1")
        self.assertEqual(settings.llm_model, "gpt-5.4")
        self.assertEqual(settings.llm_api_key, "core-key")
        self.assertEqual(settings.llm_transport, "node")
        self.assertEqual(settings.llm_reasoning_effort, "medium")
        self.assertEqual(settings.llm_timeout_seconds, 180)

    def test_settings_reads_translation_stage_llm_values_from_env(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://generic.example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-generic",
                "LEXICON_LLM_API_KEY": "generic-key",
                "LEXICON_TRANSLATIONS_LLM_BASE_URL": "https://translations.example.test/v1",
                "LEXICON_TRANSLATIONS_LLM_MODEL": "gpt-5.4-mini",
                "LEXICON_TRANSLATIONS_LLM_API_KEY": "translations-key",
                "LEXICON_TRANSLATIONS_LLM_TRANSPORT": "python",
                "LEXICON_TRANSLATIONS_LLM_REASONING_EFFORT": "low",
                "LEXICON_TRANSLATIONS_LLM_TIMEOUT_SECONDS": "90",
            },
            stage="translations",
        )

        self.assertEqual(settings.llm_base_url, "https://translations.example.test/v1")
        self.assertEqual(settings.llm_model, "gpt-5.4-mini")
        self.assertEqual(settings.llm_api_key, "translations-key")
        self.assertEqual(settings.llm_transport, "python")
        self.assertEqual(settings.llm_reasoning_effort, "low")
        self.assertEqual(settings.llm_timeout_seconds, 90)

    def test_stage_settings_fall_back_to_generic_llm_values_when_stage_vars_missing(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://generic.example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-generic",
                "LEXICON_LLM_API_KEY": "generic-key",
                "LEXICON_LLM_TRANSPORT": "python",
                "LEXICON_LLM_REASONING_EFFORT": "none",
                "LEXICON_LLM_TIMEOUT_SECONDS": "75",
            },
            stage="translations",
        )

        self.assertEqual(settings.llm_base_url, "https://generic.example.test/v1")
        self.assertEqual(settings.llm_model, "gpt-generic")
        self.assertEqual(settings.llm_api_key, "generic-key")
        self.assertEqual(settings.llm_transport, "python")
        self.assertEqual(settings.llm_reasoning_effort, "none")
        self.assertEqual(settings.llm_timeout_seconds, 75)


if __name__ == "__main__":
    unittest.main()
