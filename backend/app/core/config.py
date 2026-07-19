from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App configuration, overridable via environment variables.

    Local Postgres runs on host port 5433 (5432 is taken by another service);
    CI overrides these URLs via environment variables.
    """

    database_url: str = "postgresql+asyncpg://rental:rental@localhost:5433/rental"
    test_database_url: str = "postgresql+asyncpg://rental:rental@localhost:5433/rental_test"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 30


settings = Settings()
