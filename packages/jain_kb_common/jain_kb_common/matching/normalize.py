from __future__ import annotations

import re
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

    # Rule 8b: Devanagari chandrabindu (U+0901). Apabhramsha-era OCR (e.g.
    # परमात्मप्रकाश) emits chandrabindu inconsistently — `सण्णाणेँ` in the
    # gatha vs `सण्णाणे` in the JainKosh extract is a representative case.
    # Treat like visarga/avagraha and strip so both forms collapse identically.
    if cp == 0x0901:
        return True

    return False


_NASAL_CONS = frozenset({0x0919, 0x091E, 0x0923, 0x0928, 0x092E})  # ङ ञ ण न म
_ANUSVARA = "ं"
_HALANT = "्"

# Sandhi class → nasal char. Anusvara before a consonant in class X becomes
# the corresponding class-nasal + halant (e.g. ं + क → ङ्क, ं + त → न्त).
# Class boundaries (Devanagari block):
#   0x0915–0x0919  क-class → ङ्
#   0x091A–0x091E  च-class → ञ्
#   0x091F–0x0923  ट-class → ण्
#   0x0924–0x0928  त-class → न्
#   0x092A–0x092E  प-class → म्
# For semivowels/sibilants/ह (0x092F–0x0939) and क़-ज़ extras the standard
# convention varies — we canonicalize to न् so both sides land in the same
# form.
def _nasal_for_class(cp: int) -> str | None:
    if 0x0915 <= cp <= 0x0919: return "ङ"
    if 0x091A <= cp <= 0x091E: return "ञ"
    if 0x091F <= cp <= 0x0923: return "ण"
    if 0x0924 <= cp <= 0x0928: return "न"
    if 0x092A <= cp <= 0x092E: return "म"
    if 0x092F <= cp <= 0x0939: return "न"
    if 0x0958 <= cp <= 0x095F: return "न"
    return None


def _is_devanagari_consonant(ch: str) -> bool:
    cp = ord(ch)
    return 0x0915 <= cp <= 0x0939 or 0x0958 <= cp <= 0x095F


def _canonicalize_anusvara(nfc: str) -> str:
    """Replace each anusvara `ं` followed by a Devanagari consonant with the
    sandhi-class nasal + halant + consonant. Anusvara without a following
    consonant (word-final, before vowel, etc.) is left as-is and gets stripped
    later if not significant. ZWJ/ZWNJ — and any char that the strip pass would
    later remove anyway (whitespace, danda, pipe, hyphens, ASCII punctuation) —
    between the anusvara and the consonant is tolerated, so a sandhi nasal that
    one recension writes solid (`भूदंतु`) and another writes with an intervening
    space/danda (`भूदं तु`) canonicalize to the same form instead of diverging
    on whether the anusvara happened to abut the consonant.
    """
    if _ANUSVARA not in nfc:
        return nfc
    out: list[str] = []
    i = 0
    n = len(nfc)
    while i < n:
        ch = nfc[i]
        if ch == _ANUSVARA:
            j = i + 1
            while j < n and (nfc[j] in ("‌", "‍") or _is_strip_char(nfc[j])):
                j += 1
            if j < n and _is_devanagari_consonant(nfc[j]):
                nas = _nasal_for_class(ord(nfc[j]))
                if nas is not None:
                    out.append(nas)
                    out.append(_HALANT)
                    i += 1
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


# Rule 11: collapse the old Sanskrit orthographic gemination of a consonant
# after `र्` (e.g. `पर्य्याय` ↔ `पर्याय`, `धर्म्म` ↔ `धर्म`, `कर्म्म` ↔ `कर्म`).
# Pattern: र ् C ् C  →  र ् C  (same consonant repeated, joined by halant).
# Scoped to "after र्" specifically so legitimate same-consonant conjuncts
# elsewhere (e.g. क्क in मक्का) are untouched. ZWJ/ZWNJ between the doubled
# consonant and halant is tolerated.
_RA_GEMINATE_RE = re.compile(
    r"र्([क-ह])[‌‍]*्[‌‍]*\1"
)


def _collapse_ra_gemination(s: str) -> str:
    if "र्" not in s:
        return s
    prev = None
    cur = s
    while prev != cur:
        prev = cur
        cur = _RA_GEMINATE_RE.sub(r"र्\1", cur)
    return cur


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
    # Rule 9: Vedic Sign Tiryak (U+1CED) appears in OCR'd corpus as a
    # halant look-alike — substitute with the real halant (U+094D).
    if "᳭" in nfc:
        nfc = nfc.replace("᳭", "्")
    # Rule 10: canonicalize anusvara `ं` before a consonant to the
    # corresponding sandhi-class nasal + halant (e.g. ं+ब → म्+ब). This makes
    # the anusvara form and the spelled-out form match without over-stripping
    # real nasal+consonant conjuncts (e.g. म्य in अभ्युपगम्य stays distinct
    # from a nasalization, since अभ्युपगम has no anusvara to convert).
    nfc = _canonicalize_anusvara(nfc)
    # Rule 11: collapse OCR/orthographic gemination after र् (पर्य्याय → पर्याय).
    nfc = _collapse_ra_gemination(nfc)
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
