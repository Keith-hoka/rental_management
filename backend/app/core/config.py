from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, overridable via environment variables or a .env file.

    Local Postgres runs on host port 5433 (5432 is taken by another service);
    CI overrides these URLs via environment variables.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://rental:rental@localhost:5433/rental"
    test_database_url: str = "postgresql+asyncpg://rental:rental@localhost:5433/rental_test"
    jwt_secret: str = "dev-secret-change-in-production-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 30

    # Email: when resend_api_key is set, emails are sent via Resend;
    # otherwise send_email logs the message (development).
    resend_api_key: str = ""
    email_from: str = "onboarding@resend.dev"
    frontend_url: str = "http://localhost:3000"

    # Lease-expiry reminders: daily job thresholds (days before end_date) and run hour.
    reminders_enabled: bool = True
    reminder_thresholds: list[int] = [60, 30, 7]
    reminder_hour: int = 8

    # Directory where uploaded property images are stored (served at /uploads).
    upload_dir: str = "uploads"


settings = Settings()
