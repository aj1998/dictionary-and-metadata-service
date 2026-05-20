from __future__ import annotations

import unicodedata

ZWJ = "‍"
ZWNJ = "‌"


def nfc(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace(ZWJ, "").replace(ZWNJ, "")
    return s.strip()


# Order matters — longer suffixes first.
HINDI_SUFFIXES = [
    "ियाँ", "ियों", "ोंमें", "ोंकी", "ोंका", "ोंके",
    "ें", "ों", "ाओं", "ाएँ", "ाएं",
    "ीं", "ी", "ये", "या",
    "का", "के", "की", "में", "से", "पर", "को",
    "ा", "े", "ो",
]


def strip_one_suffix(token: str) -> str:
    for suf in HINDI_SUFFIXES:
        if token.endswith(suf) and len(token) > len(suf) + 1:
            return token[: -len(suf)]
    return token
