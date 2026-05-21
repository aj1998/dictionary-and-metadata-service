# 08 — User Accounts

Optional login. Everything readable remains public; auth unlocks personalisation and writes (saved highlights, scratch pads, exports of customised PDFs).

## Auth surface

| Method | v1? | Notes |
|---|---|---|
| Email + magic-link / OTP | ✅ | Default. Email via Resend/Postmark or SES. |
| Google OAuth | ✅ | Wide reach in India. |
| Phone + OTP (India) | 🔜 | Useful but adds SMS cost; defer. |
| SSO (institutional) | future | For Jain study groups / universities. |

JWT sessions (httpOnly cookie) with refresh tokens. New `auth-service` (port 8005). Spec: `design/scope/01_user_accounts_spec.md`.

## What a logged-in user gets

| Feature | Storage |
|---|---|
| Default language preference (Hi/En + optional overlay Kn/Gu/Sa/Pr) | `user_preferences.lang_default`, `lang_overlay` |
| Default font size, theme (light/dark/sepia), reading layout density | `user_preferences.ui` (JSONB) |
| Default shastra layout variant per family | `user_preferences.layout_variants` |
| Saved graph views | `saved_views` (PG, references nodes by `natural_key`) |
| Saved highlights / bookmarks per gatha | `saved_highlights` |
| Private scratchpad notes per research tool | `user_scratchpads` (Mongo) |
| Export history (PDFs, audio downloads) | `export_history` |
| Saved AI chats (threads) | `chat_sessions` |

## What stays public (no login required)

- Read everything (shastras, dictionary, topics, graph, AI page chat in ephemeral mode).
- One-off PDF exports (without watermark of user name).
- Audio playback (streaming).

## Customisation knobs

- Per-page font size + line height.
- Devanagari font choice (Noto Serif / Noto Sans / Sanskrit-2003 / Mukta).
- Per-language script (e.g. Sanskrit in Devanagari vs. IAST romanisation).
- Citation density (compact vs. verbose).
- Auto-translate UI toggle (use AI to translate any unencountered string to user's language overlay on the fly).
- Default model in AI page (base vs. finetuned).

## Roles

| Role | Powers |
|---|---|
| `guest` | Read public content. |
| `user` | Above + personalisation, scratchpad, saved highlights, export. |
| `reviewer` | Above + review queues (translation candidates, topic candidates, drush-taant images, audio chapters). |
| `admin` | Above + ingestion triggers, model registry, finetune jobs, layout config editor, role management. |
| `service` | Internal service-to-service tokens (no UI). |

## Privacy

- Email is the only PII collected by default.
- All AI chat threads default to "private to user"; user can mark a thread public to share via link.
- No third-party analytics; self-hosted Plausible/Umami.
- Right-to-delete: account deletion drops `users` row, all `user_*` tables, soft-anonymises chat logs (keeps query text without user id for retrieval improvement, configurable).

## Definition of done

- [ ] Email magic-link signup + Google OAuth both working.
- [ ] `user_preferences` round-trips on language change.
- [ ] Saved highlights persist + render on the gatha page.
- [ ] Reviewer role can act on the translation review queue.
- [ ] Account deletion endpoint wipes all tables and queues anonymisation.
