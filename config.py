from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str = "super-secret-key-32chars-prod!!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    INR_TO_USD_RATE: float = 83.5
    ROUNDING_TOLERANCE: float = 0.02  # 2 paise tolerance

settings = Settings()
