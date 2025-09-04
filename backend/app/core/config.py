from pydantic_settings import BaseSettings
from typing import Set
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "Meeting Transcriber API"
    VERSION: str = "0.1.0"
    
    # Whisper settings
    WHISPER_MODEL: str = "base"  # Minimal fallback
    COMPUTE_TYPE: str = "int8"   # Safe default
    
    # Pyannote settings
    USE_SPEAKER_DIARIZATION: bool = False  # Safe default (disabled)
    # Options: 'auto' (try offline then online), 'offline' (local only), 'online' (requires token)
    DIARIZATION_MODE: str = "auto"
    # Pyannote settings - default to SD 3.1
    PYANNOTE_SEGMENTATION_MODEL: str = "pyannote/speaker-diarization-3.1"
    PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH: str = str(Path.home() / ".cache/huggingface/pyannote/sd3.1/pyannote-models/models--pyannote--speaker-diarization-3.1")
    DIARIZATION_MIN_SPEAKERS: int = 1
    DIARIZATION_MAX_SPEAKERS: int = 10
     
    # File settings (hardcoded paths)
    INTERMEDIATE_FOLDER: str = "backend/intermediate"
    FINAL_OUTPUT_FOLDER: str = "finaloutput"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB fallback
    ALLOWED_EXTENSIONS: Set[str] = {"wav", "mp3", "m4a", "mp4", "ogg", "flac", "mov"}
    
    # Audio processing settings
    STANDARD_SAMPLE_RATE: int = 16000
    STANDARD_CHANNELS: int = 1
    STANDARD_FORMAT: str = "wav"
    
    # HuggingFace - must be set in .env or environment
    HUGGINGFACE_TOKEN: str = ""
    
    # Ollama settings for meeting notes - fallbacks for local development
    OLLAMA_MODEL: str = "llama2"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    
    # Logging settings
    LOG_LEVEL: str = "WARNING"
    
    @property
    def project_root(self) -> Path:
        """Get the project root directory (parent of backend folder)"""
        return Path(__file__).parent.parent.parent.parent
    
    @property
    def upload_folder_path(self) -> Path:
        """Get the full path to upload folder (hardcoded to 'uploads')"""
        return self.project_root / "uploads"
    
    @property
    def final_output_folder_path(self) -> Path:
        """Get the full path to final output folder relative to project root"""
        return self.project_root / self.FINAL_OUTPUT_FOLDER
    
    @property
    def intermediate_folder_path(self) -> Path:
        """Get the full path to intermediate folder relative to project root"""
        return self.project_root / self.INTERMEDIATE_FOLDER
    
    @property
    def logs_folder_path(self) -> Path:
        """Get the full path to logs folder relative to project root"""
        return self.project_root / "logs"
    
    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")  # backend/.env
        case_sensitive = True
        env_file_encoding = 'utf-8'
        extra = 'ignore'
        
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ):
            # Priority order: init_settings > environment > .env > file secrets
            return (
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
            )

# Create settings instance - pydantic-settings handles env vars and .env file automatically
settings = Settings()
