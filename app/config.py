import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./league.db")
    secret_key: str = os.getenv("SECRET_KEY", "dev-only-secret-change-me-in-production-0000")
    token_expire_minutes: int = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))
    max_tickets_per_booking: int = int(os.getenv("MAX_TICKETS_PER_BOOKING", "8"))
    # Bookings can be cancelled until this many hours before kickoff.
    cancel_cutoff_hours: int = int(os.getenv("CANCEL_CUTOFF_HOURS", "2"))
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@league.local")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin1234")
    seed_on_startup: bool = os.getenv("SEED_ON_STARTUP", "1") == "1"


settings = Settings()
