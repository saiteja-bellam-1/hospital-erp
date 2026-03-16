from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "KT HEALTH ERP"
    debug: bool = True
    secret_key: str = "hospital-erp-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours
    
    class Config:
        env_file = ".env"

settings = Settings()