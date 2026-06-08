import json
from functools import cache
from pathlib import Path
from typing import Literal, Optional

from bot.utils.encoding import generate_id, xor_encode

ChallengeDict = Literal["normal", "hard", "full"]

DICT_ORDER: list[ChallengeDict] = ["normal", "hard", "full"]

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


def get_dict_hints(
    word: str, selected: ChallengeDict
) -> dict[str, Optional[ChallengeDict]]:
    selected_idx = DICT_ORDER.index(selected)
    in_selected = is_word_in_dict(word, selected)

    if not in_selected:
        found_in = next(
            (d for d in DICT_ORDER if d != selected and is_word_in_dict(word, d)),
            None,
        )
        return {"found_in": found_in, "easier_than": None}

    easier_than = next(
        (d for d in DICT_ORDER[:selected_idx] if is_word_in_dict(word, d)),
        None,
    )
    return {"found_in": None, "easier_than": easier_than}


def encode_challenge(
    word: str, dict_type: ChallengeDict, guesses: int
) -> tuple[str, str]:
    challenge_id = generate_id()
    config = {
        "word": word.upper(),
        "dict": dict_type,
        "guesses": guesses,
        "length": len(word),
        "id": challenge_id,
    }
    encoded = xor_encode(json.dumps(config, separators=(",", ":")))
    return encoded, challenge_id


def build_challenge_url(base_url: str, encoded: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/?challenge={encoded}"
