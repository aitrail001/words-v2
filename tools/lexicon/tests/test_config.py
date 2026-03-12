import unittest
from pathlib import Path

from tools.lexicon.config import LexiconSettings


class LexiconSettingsTests(unittest.TestCase):
    def test_settings_default_output_root_uses_repo_data_dir(self) -> None:
        settings = LexiconSettings.from_env({})

        self.assertEqual(settings.output_root, Path("data/lexicon"))
        self.assertEqual(settings.llm_timeout_seconds, 60)

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

    def test_settings_rejects_invalid_reasoning_effort(self) -> None:
        with self.assertRaises(ValueError):
            LexiconSettings.from_env({"LEXICON_LLM_REASONING_EFFORT": "turbo"})


if __name__ == "__main__":
    unittest.main()
