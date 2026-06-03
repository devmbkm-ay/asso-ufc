from pydantic_settings import BaseSettings
from pydantic import EmailStr


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Asso API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/asso_db"

    # JWT
    SECRET_KEY: str = "changeme-generate-a-strong-secret-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Email (Brevo)
    BREVO_API_KEY: str = ""
    EMAIL_FROM: EmailStr = "noreply@asso.fr"
    EMAIL_FROM_NAME: str = "Association"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
