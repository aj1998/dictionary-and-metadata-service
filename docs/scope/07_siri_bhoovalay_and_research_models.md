# 07 — Siri Bhoovalay & Research Models

The research workstreams that ride on top of the graph + finetuned models. Two flavours: a custom **Siri Bhoovalay decoder workspace**, and a family of **domain-specific research tools** (Maths, Sciences, Philosophy, Astronomy, Ethics).

## Siri Bhoovalay decoding workspace

The Siri Bhoovalay (श्री भूवलय) is a cryptographic Jain text composed by Acharya Kumudendu in old Kannada. It encodes 718 languages in a numerical grid (chakras of 27×27 cells). Modern decoders read these in spiral / serpentine patterns.

### Workspace pieces

| Pane | Function |
|---|---|
| **Chakra viewer** | Interactive 27×27 grid. Numbers 1–64 mapped to Kannada / Sanskrit / Prakrit syllables (mapping table is configurable). |
| **Pattern picker** | Pre-canned reading patterns (horizontal, vertical, diagonal, spiral, knight's-move, etc.); user can sketch a custom path. |
| **Decoded output panel** | The syllable stream produced by the current path, plus a "guess language" toggle that uses the language models. |
| **Comparison panel** | Side-by-side: candidate decoded text vs. known passages from other shastras (semantic similarity via embeddings). |
| **LLM helper** | Uses the Sanskrit + Prakrit finetuned models (spec 26) + a small "cryptanalysis assistant" finetune to suggest plausible patterns/language identifications. |
| **Note pad** | User saves a pattern + decoded text + interpretation. Searchable. |

### Data

- Numerical grids of the existing 1270 chakras digitised manually (out of scope: digitisation itself — assume input file is available or stub-loaded).
- Syllable mapping tables (multiple competing decoders; user picks one).
- Cross-references to other shastras' passages (graph-linked once decoded).

### Cryptographic modelling

Out of v1 scope to *break* the bhoovalay; v1 scope is to provide a *workspace* that makes decoding faster. The "cryptanalysis assistant" is at most a finetuned LLM that can score pattern hypotheses against language-model perplexity in the candidate language — not a novel cryptographic algorithm.

Spec: `design/scope/27_siri_bhoovalay_workspace_spec.md`.

## Research models — index

Each model is a finetune from the Jainism main checkpoint (see [06](./06_advanced_rag_and_finetuning.md)), specialised by domain.

### Jain + Modern Maths

- Inputs: Jain canonical mathematical content (e.g. *Trilokasaar* numerology, Karm computations, samay-anavshakaras, infinite-series treatments) + modern algebra/number-theory textbooks.
- Tasks: solve a Jain maths problem; translate Jain numerology into modern notation; explain Jain treatment of infinity vs. Cantor's; etc.
- Tool integration: a calculator + symbolic-maths panel side-by-side with the chat.

### Jain + Modern Sciences (Physics, Chemistry, Biology)

- Three separate finetunes from the main checkpoint.
- Physics: jeev/ajeev classification, pudgal-paryay theory, gati/sthiti karm dynamics ↔ modern matter/energy.
- Chemistry: pudgal varga, paramaanu theory ↔ atomic theory.
- Biology: jeev classification (ekendriya → panchendriya), kayasthiti ↔ taxonomy.
- Tool integration: interactive comparison tables, citation panel.

### Jain Astronomy / Teenlok + 3D model

- Inputs: Tiloyapannatti, Trilokasaar, Lokvibhag.
- 3D viewer: render of the Jain cosmological model (urdhva/madhya/adho lok), with click-through to canonical citations.
- Model: finetuned for measurement queries (yojan, rajju, etc.) and locations.

### Jain + Modern Philosophy

- Inputs: ShatDarshan content (Nyaya, Vaisheshika, Sankhya, Yoga, Mimamsa, Vedanta) + Jain Darshan + Western philosophy primers.
- Tasks: comparative answers ("How does Anekantvad differ from Hegelian dialectic?").

### Jain + Modern Ethics & Practical Life

- Inputs: shravakachar, anuvrat content + modern applied-ethics case studies.
- Tasks: situational Q/A ("Is this business decision compatible with anuvrat?").

### Sanskrit / Prakrit / Kn / Gu / Ta — language models

Already covered in [06](./06_advanced_rag_and_finetuning.md). Reused here for Siri Bhoovalay and for the Translation Workbench.

## Research Tools framework

All research tools share the same shell (see [01_pages_and_features.md](./01_pages_and_features.md)). A new tool needs:

1. A short config registering the tool name, icon, default model from `model_registry`.
2. Optional custom panes (e.g., calculator for Maths, 3D viewer for Astronomy).
3. A scratchpad config (per-user persistence schema).

Spec: `design/scope/28_research_tools_framework_spec.md`, `29_research_models_index_spec.md`.

## Definition of done

- [ ] Siri Bhoovalay workspace renders a chakra, supports ≥ 4 pre-canned patterns, plays back syllable stream.
- [ ] Maths research tool present in catalog with one finetuned model wired up.
- [ ] At least one comparative-philosophy query produces a citation-rich answer with both Jain and modern sources.
- [ ] All research tools share the same UI shell and scratchpad backend.
