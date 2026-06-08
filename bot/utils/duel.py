import json
import random
import time
from functools import cache
from pathlib import Path
from typing import Literal

from bot.utils.encoding import generate_id, xor_encode

DuelDifficulty = Literal["normal", "hard"]

DIFFICULTY_LABELS: dict[str, str] = {
    "normal": "Normal",
    "hard": "Hard",
}

DIFFICULTY_CONFIG: dict[str, dict] = {
    "normal": {"guesses": 11, "dict": "normal"},
    "hard": {"guesses": 9, "dict": "hard"},
}

_WORDS_DIR = Path(__file__).parent


@cache
def _load_word_lists() -> tuple[list[str], list[str]]:
    normal = json.loads((_WORDS_DIR / "words_normal.json").read_text())
    hard = json.loads((_WORDS_DIR / "words_hard.json").read_text())
    return normal, hard


def get_random_word(difficulty: DuelDifficulty, length: int) -> str | None:
    normal_words, hard_words = _load_word_lists()
    pool = normal_words if difficulty == "normal" else hard_words
    filtered = [w for w in pool if len(w) == length]
    if not filtered:
        return None
    return random.choice(filtered).upper()


def generate_duel_id() -> str:
    return generate_id()


def encode_duel(
    word: str, difficulty: DuelDifficulty, duel_id: str, discord_id: str
) -> str:
    cfg = DIFFICULTY_CONFIG[difficulty]
    payload = {
        "word": word.upper(),
        "dict": cfg["dict"],
        "guesses": cfg["guesses"],
        "length": len(word),
        "id": duel_id,
        "discord_id": discord_id,
        "created_at": int(time.time() * 1000),
    }
    return xor_encode(json.dumps(payload, separators=(",", ":")))


def build_duel_url(base_url: str, encoded: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/?duel={encoded}"


def create_duel_links(
    word: str,
    difficulty: DuelDifficulty,
    player1_discord_id: str,
    player2_discord_id: str,
) -> tuple[str, str, str]:
    duel_id = generate_duel_id()
    encoded1 = encode_duel(word, difficulty, duel_id, player1_discord_id)
    encoded2 = encode_duel(word, difficulty, duel_id, player2_discord_id)
    return duel_id, encoded1, encoded2
