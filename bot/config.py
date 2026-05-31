import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    CLOUDFLARE_NAMESPACE_ID = os.getenv("CLOUDFLARE_NAMESPACE_ID")
    CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
    CLOUDFLARE_D1_DATABASE_ID = os.getenv("CLOUDFLARE_D1_DATABASE_ID")
    STATS_CHANNEL_ID = int(os.getenv("STATS_CHANNEL_ID", 0)) or None
    FEEDBACK_CHANNEL_ID = int(os.getenv("FEEDBACK_CHANNEL_ID", 0)) or None
    SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID", 0)) or None
    GUILD_ID = int(os.getenv("GUILD_ID", 0)) or None
    CURSEFORGE_API_KEY = os.getenv("CURSEFORGE_API_KEY")
    CURSEFORGE_AUTHOR_ID = os.getenv("CURSEFORGE_AUTHOR_ID")
    VAGUDLE_URL = "https://vagudle.king-tajin.dev"
    CHALLENGE_KEY = os.getenv("CHALLENGE_KEY", "test")
    DUEL_WEBHOOK_SECRET = os.getenv("DUEL_WEBHOOK_SECRET")
    DUEL_WEBHOOK_PORT = int(os.getenv("DUEL_WEBHOOK_PORT", 8079))
    ACTIVITY_APP_ID = os.getenv("CURSEFORGE_AUTHOR_ID")

    @classmethod
    def validate(cls):
        required = [
            ("DISCORD_BOT_TOKEN", cls.DISCORD_BOT_TOKEN),
            ("CLOUDFLARE_ACCOUNT_ID", cls.CLOUDFLARE_ACCOUNT_ID),
            ("CLOUDFLARE_NAMESPACE_ID", cls.CLOUDFLARE_NAMESPACE_ID),
            ("CLOUDFLARE_API_TOKEN", cls.CLOUDFLARE_API_TOKEN),
            ("DUEL_WEBHOOK_SECRET", cls.DUEL_WEBHOOK_SECRET),
            ("ACTIVITY_APP_ID", cls.ACTIVITY_APP_ID),
        ]

        missing = [name for name, value in required if not value]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return True
