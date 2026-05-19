## Additional usecases worth adding later (suggestions)

These are NOT in the v1 scope above. Captured here so the contracts above
leave room for them.

1. **Alias-driven query rewriting** — replace vernacular tokens (e.g. "आतम")
   with the canonical natural_key ("आत्मा") *before* calling
   `external_search`. Improves vector recall without changing the LLM prompt.
2. **Auto follow-up suggestions** — given the top-ranked topic, surface its
   `RELATED_TO` neighbours as suggested follow-up questions in the chat
   response.
3. **Gatha-grounded answer mode** — when a matched topic carries a
   high-weight gatha reference, auto-attach the canonical
   Prakrit+Sanskrit+Hindi+bhavarth tuple as context (replacing the noisy
   excerpt the vector path would produce).
4. **Conflict surfacing** — if two definitions of the same keyword disagree
   across sources, return both in `definitions[]` so the LLM (or UI) can
   present the conflict rather than collapsing it.
5. **Filter-name canonicalization** — kb-side normalization of shastra /
   author / teeka filter values before they reach cataloguesearch (typo
   tolerance for user filters, not just LLM-extracted ones).
6. **Citation enrichment** — post-process cataloguesearch citations to attach
   the canonical `{shastra, gatha, page}` from kb so the FE can deep-link
   into the kb graph viewer.
7. **Unknown-keyword telemetry** — log every jain-keyword that misses the
   dictionary (after fuzzy) into `topic_candidates` / a new `keyword_misses`
   table for admin curation. Closes the loop on dictionary growth.
8. **Negative dictionary** — small curated list of "looks-jain but actually
   stopword" tokens that chat should skip the dictionary check for.
9. **Per-session resolution cache** — chat caches `(token → canonical)` for
   the lifetime of the session to avoid repeated trigram calls during
   follow-ups.
10. **Cross-source disambiguation** — when both nikkyjain and JainKosh have a
    matching keyword/topic with the same natural_key but different
    definitions, return both with `source` tags so chat can label them.