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

    # Rule 5b: Unicode curly quotation marks — left/right single (U+2018/U+2019)
    # and left/right double (U+201C/U+201D). The corpus wraps embedded quotes in
    # these (e.g. the टीका writes ‘समगुणपर्यायं द्रव्यम्’) while JainKosh extracts
    # drop them, so strip them like the ASCII quotes in rule 5.
    if cp in (0x2018, 0x2019, 0x201C, 0x201D):
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


def _canonicalize_anusvara_idx(chars: list[str], idxs: list[int]) -> tuple[list[str], list[int]]:
    """Index-aware variant of anusvara canonicalization.

    Replace each anusvara `ं` followed by a Devanagari consonant with the
    sandhi-class nasal + halant + consonant. A *word-final* anusvara — one not
    followed by a consonant (string end, before a vowel, etc.) — is canonicalized
    to `म्` instead, since in Sanskrit/Prakrit a word-final anusvara represents
    म् (e.g. `द्रव्यं` ≡ `द्रव्यम्`, `अहं` ≡ `अहम्`). ZWJ/ZWNJ — and any char that
    the strip pass would later remove anyway (whitespace, danda, pipe, hyphens,
    ASCII punctuation) — between the anusvara and the next letter is tolerated,
    so a sandhi nasal that one recension writes solid (`भूदंतु`) and another
    writes with an intervening space/danda (`भूदं तु`) canonicalize to the same
    form instead of diverging on whether the anusvara happened to abut the
    consonant. The word-final rule is likewise space-tolerant: `द्रव्यं इति`
    (anusvara + space + vowel) collapses to the same form as `द्रव्यम् इति`.

    Operates on parallel (chars, idxs) lists, where `idxs[k]` is the raw-NFC
    offset of `chars[k]`. The injected nasal + halant both inherit the anusvara's
    raw offset, so downstream `n2o` stays anchored to the un-transformed text the
    UI renders.
    """
    if _ANUSVARA not in chars:
        return chars, idxs
    out_c: list[str] = []
    out_i: list[int] = []
    i = 0
    n = len(chars)
    while i < n:
        ch = chars[i]
        if ch == _ANUSVARA:
            src = idxs[i]
            j = i + 1
            while j < n and (chars[j] in ("‌", "‍") or _is_strip_char(chars[j])):
                j += 1
            if j < n and _is_devanagari_consonant(chars[j]):
                nas = _nasal_for_class(ord(chars[j]))
                if nas is not None:
                    out_c.append(nas); out_i.append(src)
                    out_c.append(_HALANT); out_i.append(src)
                    i += 1
                    continue
            else:
                # Word-final / pre-vowel anusvara → म् (Sanskrit/Prakrit
                # convention). Makes `द्रव्यं` and the spelled-out `द्रव्यम्`
                # collapse identically.
                out_c.append("म"); out_i.append(src)
                out_c.append(_HALANT); out_i.append(src)
                i += 1
                continue
        out_c.append(ch); out_i.append(idxs[i])
        i += 1
    return out_c, out_i


# Rule 11: collapse the old Sanskrit orthographic gemination of a consonant
# after `र्` (e.g. `पर्य्याय` ↔ `पर्याय`, `धर्म्म` ↔ `धर्म`, `कर्म्म` ↔ `कर्म`).
# Pattern: र ् C ् C  →  र ् C  (same consonant repeated, joined by halant).
# Scoped to "after र्" specifically so legitimate same-consonant conjuncts
# elsewhere (e.g. क्क in मक्का) are untouched. ZWJ/ZWNJ between the doubled
# consonant and halant is tolerated.
_RA_GEMINATE_RE = re.compile(
    r"र्([क-ह])[‌‍]*्[‌‍]*\1"
)


def _is_zw(ch: str) -> bool:
    return ch in ("‌", "‍")


def _collapse_ra_gemination_idx(chars: list[str], idxs: list[int]) -> tuple[list[str], list[int]]:
    """Index-aware र्-gemination collapse (पर्य्याय → पर्याय, धर्म्म → धर्म).

    Mirrors the `र्([क-ह])[‌‍]*्[‌‍]*\\1 → र्\\1` rewrite but on parallel
    (chars, idxs) lists so the surviving characters keep their raw-NFC offsets.
    The dropped run (second halant + duplicate consonant, plus any ZWJ/ZWNJ) is
    simply not copied. Runs to a fixed point to handle chains.
    """
    if "र" not in chars:
        return chars, idxs
    prev_len = -1
    while len(chars) != prev_len:
        prev_len = len(chars)
        out_c: list[str] = []
        out_i: list[int] = []
        n = len(chars)
        i = 0
        while i < n:
            # Match र ् C  at i, i+1, i+2
            if (
                i + 2 < n
                and chars[i] == "र"
                and chars[i + 1] == _HALANT
                and _is_devanagari_consonant(chars[i + 2])
            ):
                cons = chars[i + 2]
                k = i + 3
                while k < n and _is_zw(chars[k]):
                    k += 1
                if k < n and chars[k] == _HALANT:
                    k += 1
                    while k < n and _is_zw(chars[k]):
                        k += 1
                    if k < n and chars[k] == cons:
                        # Keep र ् C, drop the trailing ्…C duplicate.
                        out_c.append(chars[i]); out_i.append(idxs[i])
                        out_c.append(chars[i + 1]); out_i.append(idxs[i + 1])
                        out_c.append(chars[i + 2]); out_i.append(idxs[i + 2])
                        i = k + 1
                        continue
            out_c.append(chars[i]); out_i.append(idxs[i])
            i += 1
        chars, idxs = out_c, out_i
    return chars, idxs


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
      6. All digits (ASCII + Devanagari) — verse markers, glued or not
      7. Devanagari avagraha
    """
    nfc = unicodedata.normalize("NFC", text)
    # `original` is kept as the RAW NFC text — the same coordinate space the UI
    # renders (it applies `normalizeNFC(text)` then slices by char offsets). The
    # length-changing canonicalizations below therefore track each working
    # character's raw-NFC offset in a parallel `idxs` list, so the final `n2o`
    # maps normalized indices back to raw NFC — NOT to the transformed string.
    # (Reporting offsets in the transformed space caused the highlight to drift
    # forward by one char per anusvara/gemination edit before the match.)
    work_c: list[str] = []
    work_i: list[int] = []
    for i, ch in enumerate(nfc):
        # Rule 9: Vedic Sign Tiryak (U+1CED) appears in OCR'd corpus as a
        # halant look-alike — substitute with the real halant (U+094D).
        work_c.append("्" if ch == "᳭" else ch)
        work_i.append(i)

    # Rule 10: canonicalize anusvara `ं` (before a consonant → sandhi-class
    # nasal + halant; word-final → म्). Makes the anusvara form and the
    # spelled-out form match without over-stripping real nasal+consonant
    # conjuncts.
    work_c, work_i = _canonicalize_anusvara_idx(work_c, work_i)
    # Rule 11: collapse OCR/orthographic gemination after र् (पर्य्याय → पर्याय).
    work_c, work_i = _collapse_ra_gemination_idx(work_c, work_i)

    n = len(work_c)
    strip = [False] * n

    # Pass 1: mark by rules 1–5, 7
    for i, ch in enumerate(work_c):
        if _is_strip_char(ch):
            strip[i] = True

    # Pass 2: rule 6 — strip ALL digits unconditionally (ASCII + Devanagari).
    # The corpus glues verse markers to text in inconsistent ways (`।1।`, `|1|`,
    # `गाथा9`, digits abutting a word with no separating danda), so a
    # bounded-only rule left stray digits that broke matching. JainKosh extracts
    # and NJ targets never carry semantically-meaningful inline digits, so we
    # drop every digit so both sides collapse identically.
    for i in range(n):
        if _is_digit(work_c[i]):
            strip[i] = True

    # Build output — n2o carries the raw-NFC offset of each surviving char.
    chars: list[str] = []
    n2o: list[int] = []
    for i, ch in enumerate(work_c):
        if not strip[i]:
            chars.append(ch)
            n2o.append(work_i[i])

    return NormalizedText(
        original=nfc,
        normalized="".join(chars),
        n2o=n2o,
    )
