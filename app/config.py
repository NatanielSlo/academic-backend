import os
import yaml
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class LLMConfig(BaseSettings):
    provider: str
    models: dict[str, str]
    api_key: str


class OpenAIConfig(BaseSettings):
    api_key: str
    whisper_model: str
    embedding_model: str


class GroqConfig(BaseSettings):
    api_key: str
    whisper_model: str


class TranscriptionConfig(BaseSettings):
    provider: str  # "openai" or "groq"
    language: str | None = None  # Language code (e.g., "de", "en") or None for auto-detect


class DatabaseConfig(BaseSettings):
    url: str


class ChunkingConfig(BaseSettings):
    chunk_size: int
    overlap: int


class RAGConfig(BaseSettings):
    top_k: int
    similarity_threshold: float
    use_reranking: bool = False
    prompt_version: str = "v2"
    preprocess_query: bool = True


class AudioConfig(BaseSettings):
    output_dir: str
    allowed_domains: list[str]


class Config(BaseSettings):
    llm: LLMConfig
    openai: OpenAIConfig
    groq: GroqConfig
    transcription: TranscriptionConfig
    database: DatabaseConfig
    chunking: ChunkingConfig
    rag: RAGConfig
    audio: AudioConfig

    @classmethod
    def load_from_yaml(cls, config_path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file with environment variable substitution."""
        with open(config_path, "r") as f:
            config_dict = yaml.safe_load(f)

        # Recursively substitute environment variables
        config_dict = cls._substitute_env_vars(config_dict)

        return cls(**config_dict)

    @classmethod
    def _substitute_env_vars(cls, obj):
        """Recursively substitute ${VAR} patterns with environment variables."""
        if isinstance(obj, dict):
            return {k: cls._substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [cls._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            return os.getenv(env_var, obj)
        return obj


# Global config instance
config = Config.load_from_yaml()
