from __future__ import annotations

import unicodedata


def java_is_blank(value: str) -> bool:
    """Match Java String.isBlank without inheriting Python whitespace rules."""
    return all(_java_character_is_whitespace(char) for char in value)


def java_trim(value: str) -> str:
    """Match Java String.trim, which removes only UTF-16 units through U+0020."""
    start = 0
    end = len(value)
    while start < end and ord(value[start]) <= 0x20:
        start += 1
    while end > start and ord(value[end - 1]) <= 0x20:
        end -= 1
    return value[start:end]


def java_utf16_length(value: str) -> int:
    """Match Java String.length, which counts UTF-16 code units."""
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def _java_character_is_whitespace(char: str) -> bool:
    code_point = ord(char)
    if 0x09 <= code_point <= 0x0D or 0x1C <= code_point <= 0x1F:
        return True
    if char in {"\u00a0", "\u2007", "\u202f"}:
        return False
    return unicodedata.category(char) in {"Zs", "Zl", "Zp"}
