from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    
       # Database
    DATABASE_URL: str
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    
    # Google AI
    GOOGLE_API_KEY: str
    
    # JWT Configuration
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 10080  # 7 days
    
    # Frontend URL
    FRONTEND_URL: str = "http://localhost:8000"
    
    # Environment
    ENVIRONMENT: str = "development"
    
    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8000",
    ]
    
    # API Configuration
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "CodeMate AI"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "A RAG-powered chatbot with Google Docs/Sheets/Slides integration"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# Create global settings instance
settings = Settings()

# Validate settings on startup
def validate_settings():
    """Validate critical settings on startup."""
    required_fields = [
        "DATABASE_URL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_API_KEY",
        "JWT_SECRET_KEY",
    ]
    
    missing_fields = []
    for field in required_fields:
        if not getattr(settings, field, None):
            missing_fields.append(field)
    
    if missing_fields:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_fields)}\n"
            f"Please check your .env file."
        )
    
    print("✅ Configuration validated successfully")


# Print configuration on import (for debugging)
if settings.ENVIRONMENT == "development":
    print(f"""
    🔧 Configuration Loaded:
    - Environment: {settings.ENVIRONMENT}
    - Database: {settings.DATABASE_URL[:30]}...
    - Frontend URL: {settings.FRONTEND_URL}
    - Google OAuth: Configured
    - Google AI: Configured
    """)