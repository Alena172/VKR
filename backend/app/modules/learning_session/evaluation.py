import re
from difflib import SequenceMatcher


def normalize_answer(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_answer_correct(expected: str | None, user_answer: str | None) -> bool:
    normalized_expected = normalize_answer(expected)
    normalized_user = normalize_answer(user_answer)
    if not normalized_expected:
        return False
    if normalized_expected == normalized_user:
        return True

    expected_tokens = normalized_expected.split()
    user_tokens = normalized_user.split()
    if not expected_tokens or not user_tokens:
        return False

    # Single-word answers stay strict to avoid accidental false positives.
    if len(expected_tokens) == 1 or len(user_tokens) == 1:
        return False

    # For sentence translation tasks we allow close paraphrases:
    # small lexical variation with preserved overall meaning/structure.
    text_similarity = SequenceMatcher(None, normalized_expected, normalized_user).ratio()
    expected_token_set = set(expected_tokens)
    user_token_set = set(user_tokens)
    token_recall = len(expected_token_set & user_token_set) / max(1, len(expected_token_set))

    return text_similarity >= 0.88 and token_recall >= 0.7
