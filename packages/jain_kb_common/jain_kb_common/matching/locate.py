from __future__ import annotations

import logging

from .normalize import NormalizedText
from .score import DEFAULT_THRESHOLD, jaccard
from .types import MatchResult

logger = logging.getLogger("jain_kb.matching")

# When target is more than this factor times the source length, use strided
# sampling instead of exhaustive per-window Jaccard (bounds cost on long teekas).
# TODO: replace strided sampling with proper rolling-hash candidates when a real
#       slow case is profiled.
_SHINGLE_GUARD_FACTOR = 50


def _char_ngrams(text: str, n: int) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _no_match(src_norm: str, tgt_norm: str, score: float = 0.0) -> MatchResult:
    return MatchResult(
        matched=False,
        method="none",
        score=score,
        char_start=None,
        char_end=None,
        normalized_source=src_norm,
        normalized_target=tgt_norm,
    )


def locate(
    source: NormalizedText,
    target: NormalizedText,
    *,
    shingle_n: int = 3,
    threshold: float = DEFAULT_THRESHOLD,
) -> MatchResult:
    """
    Locate *source* inside *target* and return char offsets into the original text.

    Tries exact normalized substring first; falls back to sliding-window
    character n-gram Jaccard. Returns matched=False when the best score is
    below *threshold*.
    """
    src_norm = source.normalized
    tgt_norm = target.normalized

    logger.info(
        "locate: source_len=%d target_len=%d threshold=%.2f",
        len(src_norm),
        len(tgt_norm),
        threshold,
    )

    # Step 1: exact normalized substring
    if src_norm:
        pos = tgt_norm.find(src_norm)
        if pos >= 0:
            end_norm = pos + len(src_norm)
            char_start = target.n2o[pos]
            char_end = target.n2o[end_norm - 1] + 1
            logger.debug(
                "exact match norm[%d:%d] → orig[%d:%d]",
                pos, end_norm, char_start, char_end,
            )
            return MatchResult(
                matched=True,
                method="exact_normalized",
                score=1.0,
                char_start=char_start,
                char_end=char_end,
                normalized_source=src_norm,
                normalized_target=tgt_norm,
            )

    # Step 2: shingle fallback
    win_len = len(src_norm)
    tgt_len = len(tgt_norm)

    if win_len == 0 or tgt_len < win_len:
        return _no_match(src_norm, tgt_norm)

    src_ngrams = _char_ngrams(src_norm, shingle_n)
    best_score = 0.0
    best_start = 0
    n_windows = tgt_len - win_len + 1

    if tgt_len > _SHINGLE_GUARD_FACTOR * win_len:
        # Strided sampling to bound cost on very long target bodies.
        stride = max(1, n_windows // (_SHINGLE_GUARD_FACTOR * 5))
        positions: list[int] = list(range(0, n_windows, stride))
    else:
        positions = list(range(n_windows))

    for i in positions:
        win_ngrams = _char_ngrams(tgt_norm[i : i + win_len], shingle_n)
        score = jaccard(src_ngrams, win_ngrams)
        logger.debug("shingle i=%d score=%.4f", i, score)
        if score > best_score:
            best_score = score
            best_start = i

    if best_score < threshold:
        return _no_match(src_norm, tgt_norm, best_score)

    end_norm = best_start + win_len
    char_start = target.n2o[best_start]
    char_end = target.n2o[end_norm - 1] + 1
    logger.debug(
        "shingle match norm[%d:%d] → orig[%d:%d] score=%.4f",
        best_start, end_norm, char_start, char_end, best_score,
    )
    return MatchResult(
        matched=True,
        method="shingle_fuzzy",
        score=best_score,
        char_start=char_start,
        char_end=char_end,
        normalized_source=src_norm,
        normalized_target=tgt_norm,
    )
