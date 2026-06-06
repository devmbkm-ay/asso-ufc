from pydantic_settings import BaseSettings, SettingsConfigDict
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

    # URL publique de l'API (utilisée pour construire les URLs des fichiers uploadés)
    API_BASE_URL: str = "https://api.assos.ricardomboukou.online"

    # CORS — format JSON dans .env : ALLOWED_ORIGINS=["http://localhost:3000","https://asso.fr"]
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "https://asso-ufc-frontend.vercel.app"]

    # Cron rappels cotisations (jour du mois et heure UTC)
    REMINDER_DAY:  int = 5
    REMINDER_HOUR: int = 9

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
