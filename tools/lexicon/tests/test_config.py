import unittest
from pathlib import Path

from tools.lexicon.config import LexiconSettings


class LexiconSettingsTests(unittest.TestCase):
    def test_settings_default_output_root_uses_repo_data_dir(self) -> None:
        settings = LexiconSettings.from_env({})

        self.assertEqual(settings.output_root, Path("data/lexicon"))

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


if __name__ == "__main__":
    unittest.main()
