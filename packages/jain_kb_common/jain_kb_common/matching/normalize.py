from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


@dataclass
class NormalizedText:
    original: str           # input after NFC
    normalized: str         # stripped form used for matching
    n2o: list[int] = field(default_factory=list)  # n2o[i] = original index of normalized[i]


def _is_strip_char(ch: str) -> bool:
    """Rules 1–5, 7: chars to unconditionally strip (digit rule handled separately)."""
    cp = ord(ch)

    # Rule 1: ZWJ (U+200D), ZWNJ (U+200C)
    if cp in (0x200D, 0x200C):
        return True

    # Rule 2: ASCII whitespace + U+00A0 + all Unicode space-separator category
    if ch.isspace() or unicodedata.category(ch) == "Zs":
        return True

    # Rule 3: danda (U+0964), double-danda (U+0965), ASCII pipe
    if cp in (0x0964, 0x0965, 0x007C):
        return True

    # Rule 4: hyphen-minus, non-breaking hyphen, general punctuation hyphens/dashes
    # U+002D hyphen-minus; U+2010–U+2015 hyphen through horizontal bar;
    # U+005F underscore; U+007E tilde
    if cp == 0x002D or 0x2010 <= cp <= 0x2015 or cp in (0x005F, 0x007E):
        return True

    # Rule 5: ASCII punctuation  , . ; : ! ? " ' ( ) [ ] { } / \ * + = < > & %
    if ch in ',.;:!?"\' ()[]{}\\*+=<>&%/':
        return True

    # Rule 7: Devanagari avagraha (U+093D)
    if cp == 0x093D:
        return True

    # Rule 8: Devanagari visarga (U+0903) — corpus frequently substitutes
    # ASCII ':' for visarga, so strip both to make the two forms equivalent.
    if cp == 0x0903:
        return True

    return False


def _is_digit(ch: str) -> bool:
    cp = ord(ch)
    return ("0" <= ch <= "9") or (0x0966 <= cp <= 0x096F)


def normalize(text: str) -> NormalizedText:
    """
    Return NFC-normalized, stripped form and an offset map n2o.

    Strip rules (applied in order after NFC):
      1. ZWJ / ZWNJ
      2. Whitespace (ASCII + U+00A0 + Unicode Zs)
      3. Danda, double-danda, pipe
      4. Hyphens, dashes, underscore, tilde
      5. ASCII punctuation
      6. Digit runs surrounded by stripped chars / boundaries (verse markers)
      7. Devanagari avagraha
    """
    nfc = unicodedata.normalize("NFC", text)
    n = len(nfc)
    strip = [False] * n

    # Pass 1: mark by rules 1–5, 7
    for i, ch in enumerate(nfc):
        if _is_strip_char(ch):
            strip[i] = True

    # Pass 2: rule 6 — digit runs bounded by stripped chars (or string edge)
    i = 0
    while i < n:
        if _is_digit(nfc[i]):
            j = i
            while j < n and _is_digit(nfc[j]):
                j += 1
            left_ok = (i == 0) or strip[i - 1]
            right_ok = (j >= n) or strip[j]
            if left_ok and right_ok:
                for k in range(i, j):
                    strip[k] = True
            i = j
        else:
            i += 1

    # Build output
    chars: list[str] = []
    n2o: list[int] = []
    for i, ch in enumerate(nfc):
        if not strip[i]:
            chars.append(ch)
            n2o.append(i)

    return NormalizedText(
        original=nfc,
        normalized="".join(chars),
        n2o=n2o,
    )
