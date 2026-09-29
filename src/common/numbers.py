from __future__ import annotations


def parse_vn_number(value: str | None) -> float | None:
    """Parse Vietnamese formatted number: 32.055,15 -> 32055.15."""
    if value is None:
        return None
    text = str(value).strip().replace("\xa0", " ")
    if not text or text in {"-", "–", "—"}:
        return None
    normalized = text.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def parse_percent(value: str | None) -> float | None:
    """Parse percent while preserving dot-decimal notation.

    7,05 -> 7.05
    7.05 -> 7.05
    """
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text or text in {"-", "–", "—"}:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None
