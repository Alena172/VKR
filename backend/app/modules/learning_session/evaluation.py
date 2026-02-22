import re


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
    return normalized_expected == normalized_user

