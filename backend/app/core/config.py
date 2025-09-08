from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "compliance.db"
    secret_key: str = "complylite-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    trusted_hosts: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_prefix = "COMPLYLITE_"

settings = Settings()
