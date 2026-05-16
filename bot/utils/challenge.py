import base64
import json
import random
import string
import time
from functools import cache
from pathlib import Path
from typing import Literal

from bot.config import Config

_KEY: str = Config.CHALLENGE_KEY
_KEY_BYTES: list[int] = [ord(c) for c in _KEY]

ChallengeDict = Literal["normal", "hard", "full"]

DICT_LABELS = {
    "normal": "Normal",
    "hard": "Hard",
    "full": "Extreme",
}

DICT_DESCRIPTIONS = {
    "normal": "Common English words",
    "hard": "Uncommon English words",
    "full": "Full Scrabble dictionary",
}

_WORDS_DIR = Path(__file__).parent


@cache
def _load_sets() -> tuple[set[str], set[str], set[str]]:
    normal = set(json.loads((_WORDS_DIR / "words_normal.json").read_text()))
    hard = set(json.loads((_WORDS_DIR / "words_hard.json").read_text()))
    full = set(json.loads((_WORDS_DIR / "words_full.json").read_text()))
    return normal, hard, full


def is_word_in_dict(word: str, dict_type: ChallengeDict) -> bool:
    normal_set, hard_set, full_set = _load_sets()
    w = word.lower()

    if dict_type == "normal":
        return w in normal_set
    if dict_type == "hard":
        return w in hard_set
    return w in full_set


def _xor_encode(input_str: str) -> str:
    byte_vals = [ord(c) ^ _KEY_BYTES[i % len(_KEY_BYTES)] for i, c in enumerate(input_str)]
    binary = bytes(byte_vals)
    encoded = base64.urlsafe_b64encode(binary).decode("ascii")
    return encoded.rstrip("=")


def _generate_id() -> str:
    rand_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    time_part = hex(int(time.time() * 1000))[2:][-6:]
    return rand_part + time_part


def encode_challenge(word: str, dict_type: ChallengeDict, guesses: int) -> tuple[str, str]:
    challenge_id = _generate_id()
    config = {
        "word": word.upper(),
        "dict": dict_type,
        "guesses": guesses,
        "length": len(word),
        "id": challenge_id,
    }
    encoded = _xor_encode(json.dumps(config, separators=(",", ":")))
    return encoded, challenge_id


def build_challenge_url(base_url: str, encoded: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/?challenge={encoded}"