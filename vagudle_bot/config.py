import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN = os.getenv("VAGUDLE_BOT_TOKEN")
    STATUS_TEXT = os.getenv("VAGUDLE_BOT_STATUS_TEXT")

    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("Missing required configuration: DM_BOT_TOKEN")
        return True
