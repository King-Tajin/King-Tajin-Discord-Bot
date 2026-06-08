import base64
import random
import string
import time

from bot.config import Config

_KEY: str = Config.CHALLENGE_KEY
_KEY_BYTES: list[int] = [ord(c) for c in _KEY]


def xor_encode(input_str: str) -> str:
    byte_vals = [
        ord(c) ^ _KEY_BYTES[i % len(_KEY_BYTES)] for i, c in enumerate(input_str)
    ]
    binary = bytes(byte_vals)
    encoded = base64.urlsafe_b64encode(binary).decode("ascii")
    return encoded.rstrip("=")


def generate_id() -> str:
    rand_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    time_part = hex(int(time.time() * 1000))[2:][-6:]
    return rand_part + time_part
