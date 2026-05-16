import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    CLOUDFLARE_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    CLOUDFLARE_NAMESPACE_ID = os.getenv('CLOUDFLARE_NAMESPACE_ID')
    CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
    STATS_CHANNEL_ID = int(os.getenv('STATS_CHANNEL_ID', 0)) or None
    FEEDBACK_CHANNEL_ID = int(os.getenv('FEEDBACK_CHANNEL_ID', 0)) or None
    SUPPORT_ROLE_ID = int(os.getenv('SUPPORT_ROLE_ID', 0)) or None
    GUILD_ID = int(os.getenv('GUILD_ID', 0)) or None
    CURSEFORGE_API_KEY = os.getenv('CURSEFORGE_API_KEY')
    CURSEFORGE_AUTHOR_ID = os.getenv('CURSEFORGE_AUTHOR_ID')
    WORKER_URL = os.getenv('WORKER_URL')
    PUSH_SECRET = os.getenv('PUSH_SECRET')
    VAGUDLE_URL = "https://vagudle.king-tajin.dev"
    CHALLENGE_KEY = os.getenv('CHALLENGE_KEY', 'KTvagudle9x2challenge')

    @classmethod
    def validate(cls):
        required = [
            ('DISCORD_BOT_TOKEN', cls.DISCORD_BOT_TOKEN),
            ('CLOUDFLARE_ACCOUNT_ID', cls.CLOUDFLARE_ACCOUNT_ID),
            ('CLOUDFLARE_NAMESPACE_ID', cls.CLOUDFLARE_NAMESPACE_ID),
            ('CLOUDFLARE_API_TOKEN', cls.CLOUDFLARE_API_TOKEN),
            ('WORKER_URL', cls.WORKER_URL),
            ('PUSH_SECRET', cls.PUSH_SECRET),
        ]

        missing = [name for name, value in required if not value]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return True