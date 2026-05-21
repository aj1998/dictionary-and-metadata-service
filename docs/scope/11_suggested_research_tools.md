# 11 — Suggested Research Tools

Tools that fall naturally out of the data SAAR will have (graph + Mongo extracts + finetuned models). Each is a candidate for `#ResearchTools` catalog beyond what the brief listed.

## Canonical-text scholarship

1. **Concordance builder.** Type a Prakrit/Sanskrit/Hindi word; get every occurrence across all shastras with context windows + counter chip. Backed by the existing search + counters. Power feature for traditional scholars.
2. **Edition collator.** Pick a shastra; compare multiple published editions (publisher, year, transliteration scheme) gatha-by-gatha. Highlights textual variants. Requires ingesting more than one edition per shastra; data work, not new code.
3. **Quotation tracer.** When a teeka quotes another shastra, surface the quoted passage inline with a "compare" toggle. Builds on `references` edges that the jainkosh parser already extracts (see `design/jainkosh/reference_parser_spec.md`).
4. **Mangalacharan & colophon library.** Auto-extracts and indexes opening and closing verses across the corpus. Becomes a stand-alone browsable tool — useful for liturgical and pravachan use.
5. **Anuyoga balance dashboard.** For a chosen shastra or author, show distribution of content across the four anuyogas — visualisation derived directly from existing tags. Useful for curriculum design.

## Linguistic / philological

6. **Prakrit grammar workbench.** Companion to the `vyakaran_vishleshan` OCR pipeline. Input a Prakrit shloka; the tool runs the OCRed grammar analysis and the Sanskrit chhaaya generator side by side.
7. **Etymology explorer.** Given a Sanskrit/Prakrit root, list derived keywords + their occurrences. Leverages the same word-meaning data + a small ruleset.
8. **Sandhi splitter / joiner.** Standard NLP utility, but tuned on Jain Prakrit/Sanskrit corpus. Often missing from generic IAST tools.
9. **Transliteration converter.** Multi-script (Devanagari / IAST / ISO 15919 / Kannada / Gujarati) round-trip with diff. Useful for citations.

## Quantitative / mathematical

10. **Karm-numerology calculator.** Built on the Jain Maths model. Inputs an entity (jeev kind + bhav state) and computes karm-bondings using the canonical formulas (asankhyat, anant tiers etc.).
11. **Trilok / lokvibhag calculator.** Convert yojan ↔ km, samay ↔ second; locate places in the Jain cosmological model.
12. **Punya-paap ledger explorer.** Not a real-world ledger — a *teaching tool* that walks through karm theory step-by-step on canonical examples.

## Comparative

13. **Cross-tradition mapper.** Side-by-side terms between Jain, Buddhist, Vedantic, Yoga, Nyaya, and modern philosophy. (E.g. Atma vs. Anatta vs. Atman vs. Self.) Stub today; expandable.
14. **Modern-science mapper.** Same idea but mapping to physics/chemistry/biology terms. (E.g. paramaanu ↔ atom.) Powered by the research-domain finetuned models.
15. **Ahimsa & ethics checker.** Workspace for analysing a real-life decision against shravakachar / muniacharya principles. Strong appeal for practitioner audience.

## Historical / bibliographical

16. **Author network.** Time-line + relationship graph of acharyas, shishyas, teekakaars. Backed by existing `authors` table + new `teacher_of` edges.
17. **Manuscript provenance traces.** Where each shastra's surviving manuscripts live (collections, dates). Out-of-band data work, but the tool itself is simple.
18. **Publication timeline.** What got published in each century, by which publishers. Cards + filters; data is in `teekas.publisher`, `books.publisher`.

## Educational

19. **Curriculum builder.** Mark which gathas / topics are "level 1, 2, 3" (manual + AI suggestion); generate a reading-list PDF for a study group.
20. **Spaced-repetition deck export.** Export a topic / keyword set as Anki deck. Strong appeal to seekers in long-term swadhyay.
21. **Interactive bhaavarth quiz.** Multiple-choice on bhaavarth content with citation links to the source. Auto-generated from the topic index.

## Operational / community

22. **Reviewer leaderboard (admin)**. Internal-only — surfaces who is reviewing what. Useful for distributing the editorial load.
23. **Quality-of-source dashboard.** Coverage and confidence stats per shastra: how much is enriched, how many gathas have drush-taants, audio, English. Drives next ingestion work prioritisation.
24. **Data-gap finder.** Lists topics that have low chunk citations, low gatha mentions, or no English translation — guides future enrichment runs.

## Cross-cutting tooling

25. **Open API for tools.** Each research tool is also exposed as a JSON API endpoint — encourages outside developers to build niche tools without re-ingesting data.
26. **Plugin contract.** Define a `ResearchToolPlugin` interface (name, icon, panes, models, scratchpad-schema) so contributors can add tools by writing one config + one React component. Spec stub in `design/scope/28_research_tools_framework_spec.md`.

## What I'd consciously *not* build (yet)

- Voice-controlled tools (cute but a UX detour from serious study).
- Live multi-user collaborative tools beyond shared scratchpads (high cost; rarely the bottleneck for swadhyay).
- LLM-generated *new* gathas or commentary (very off-mission and risky).
