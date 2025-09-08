from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "compliance.db"
    secret_key: str = "complylite-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
