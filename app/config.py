from pydantic_settings import BaseSettings
from datetime import timedelta
import os

class Settings(BaseSettings):
    # JWT Settings
    SECRET_KEY: str = "legal@2025" 
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 3000
    
    # Database Settings
    DATABASE_URL: str = "sqlite:///./sql_app.db"
    
    # AWS S3 Settings
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1" 
    AWS_BUCKET_NAME: str = ""
    SENDER_EMAIL: str = ""
    ADMIN_EMAIL: str = ""

    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    
    # Payment Configuration
    STRIPE_SUCCESS_URL: str = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/payment/success")
    STRIPE_CANCEL_URL: str = os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/payment/cancel")

    @property
    def is_stripe_configured(self) -> bool:
        """Check if Stripe is properly configured"""
        return bool(
            self.STRIPE_PUBLISHABLE_KEY and 
            self.STRIPE_SECRET_KEY and 
            self.STRIPE_WEBHOOK_SECRET
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings()