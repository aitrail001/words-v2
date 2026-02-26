from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://vocabapp:devpassword@localhost:5432/vocabapp_dev"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # JWT
    jwt_secret: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30
    refresh_token_expiration_days: int = 7

    # Environment
    environment: str = "development"

    # Logging
    log_level: str = "INFO"
    log_format: str = "readable"  # "readable" or "json"

    # CORS
    allowed_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:5173"

    # Security
    bcrypt_rounds: int = 12

    # TTS Provider (minimax, elevenlabs, google, azure)
    tts_primary_provider: str = "minimax"

    # TTS Provider per audio type (word, definition, example)
    tts_provider_word: str = "google"
    tts_provider_definition: str = "google"
    tts_provider_example: str = "azure"

    # MiniMax TTS
    minimax_api_key: str = ""
    minimax_group_id: str = ""
    minimax_voice_id: str = "female-tianmei"

    # ElevenLabs TTS
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Default (Rachel)
    elevenlabs_voice_american_female: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    elevenlabs_voice_british_male: str = "onwK4e9ZLuTAKqWW03F9"  # Daniel

    # Google Cloud Text-to-Speech
    # Option 1: Path to service account JSON file
    google_application_credentials: str = ""
    # Option 2: Base64-encoded service account JSON (for containers)
    google_tts_credentials_base64: str = ""
    # Option 3: Simple API key (limited, for testing only)
    google_tts_api_key: str = ""

    # Microsoft Azure AI Speech
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"

    # Audio Storage
    audio_storage_backend: str = "local"  # local or s3
    audio_local_path: str = "uploads/audio"

    # Image Generation Provider (leonardo, replicate, openai)
    image_primary_provider: str = "leonardo"
    image_default_style: str = "simple"  # simple, illustrated, realistic, iconic

    # Image Storage
    image_storage_backend: str = "local"  # local or s3
    image_local_path: str = "uploads/images"

    # Leonardo.ai
    leonardo_api_key: str = ""

    # Replicate (FLUX models)
    replicate_api_token: str = ""
    replicate_model: str = "schnell"  # schnell, dev, pro

    # OpenAI (DALL-E) - may share key with other OpenAI services
    openai_api_key: str = ""
    openai_image_model: str = "dall-e-3"  # dall-e-3 or dall-e-2

    # LLM Provider (anthropic, openai, google)
    llm_primary_provider: str = "anthropic"
    anthropic_api_key: str = ""
    google_gemini_api_key: str = ""

    # Story Storage
    story_storage_path: str = "uploads/stories"

    # Lexicon (WordNet + LLM enhancement)
    lexicon_provider: str = "wordnet"
    lexicon_llm_enhance_on_lookup: bool = False
    lexicon_llm_provider: str = ""
    lexicon_llm_model: str = ""
    lexicon_use_external_frequency: bool = False
    lexicon_curation_enabled: bool = True
    lexicon_enrichment_enabled: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
