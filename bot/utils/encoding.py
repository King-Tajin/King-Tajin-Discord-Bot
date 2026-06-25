import base64
import hashlib
import os
import random
import string
import time

from bot.config import Config

_KEY: str = Config.CHALLENGE_KEY

def _derive_key() -> bytes:
    return hashlib.sha256(_KEY.encode()).digest()

def aes_gcm_encode(input_str: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key_bytes = _derive_key()
    aesgcm = AESGCM(key_bytes)
    iv = os.urandom(12)
    ciphertext = aesgcm.encrypt(iv, input_str.encode(), None)
    combined = iv + ciphertext
    return base64.urlsafe_b64encode(combined).decode("ascii").rstrip("=")

def generate_id() -> str:
    rand_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    time_part = hex(int(time.time() * 1000))[2:][-6:]
    return rand_part + time_part
