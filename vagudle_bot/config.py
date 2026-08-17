import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN = os.getenv("VAGUDLE_BOT_TOKEN")
    STATUS_TEXT = os.getenv("VAGUDLE_BOT_STATUS_TEXT")
    GUILD_ID = int(os.getenv("GUILD_ID", 0)) or None
    CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    CLOUDFLARE_NAMESPACE_ID = os.getenv("CLOUDFLARE_NAMESPACE_ID")
    CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
    CLOUDFLARE_D1_DATABASE_ID = os.getenv("CLOUDFLARE_D1_DATABASE_ID")
    VAGUDLE_URL = "https://vagudle.king-tajin.dev"
    CHALLENGE_KEY = os.getenv("CHALLENGE_KEY", "test")
    DAILY_EPOCH_DATE = os.getenv("DAILY_EPOCH_DATE", "2026-07-27")
    DUEL_WEBHOOK_SECRET = os.getenv("DUEL_WEBHOOK_SECRET")
    DAILY_WEBHOOK_SECRET = os.getenv("DAILY_WEBHOOK_SECRET")
    WEBHOOK_PORT = int(os.getenv("VAGUDLE_WEBHOOK_PORT", 8081))
    STATS_CHANNEL_ID = int(os.getenv("VAGUDLE_STATS_CHANNEL_ID", 0)) or None

    _raw_activity_app_id = os.getenv("ACTIVITY_APP_ID")
    ACTIVITY_APP_ID: int | None = (
        int(_raw_activity_app_id) if _raw_activity_app_id else None
    )

    @classmethod
    def validate(cls):
        required = [
            ("VAGUDLE_BOT_TOKEN", cls.BOT_TOKEN),
            ("CLOUDFLARE_ACCOUNT_ID", cls.CLOUDFLARE_ACCOUNT_ID),
            ("CLOUDFLARE_NAMESPACE_ID", cls.CLOUDFLARE_NAMESPACE_ID),
            ("CLOUDFLARE_API_TOKEN", cls.CLOUDFLARE_API_TOKEN),
            ("CLOUDFLARE_D1_DATABASE_ID", cls.CLOUDFLARE_D1_DATABASE_ID),
            ("DUEL_WEBHOOK_SECRET", cls.DUEL_WEBHOOK_SECRET),
            ("DAILY_WEBHOOK_SECRET", cls.DAILY_WEBHOOK_SECRET),
            ("ACTIVITY_APP_ID", cls.ACTIVITY_APP_ID),
        ]

        missing = [name for name, value in required if not value]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return True
