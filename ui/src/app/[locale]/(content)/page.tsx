import { ArrowRight, BookOpen, Network, ScrollText, Search, Sparkles, Tag } from '@/lib/icons';
import { Link } from '@/i18n/navigation';
import { getActivityRecent, getStatsCounts } from '@/lib/api/data';
import { toDevanagariNumerals } from '@/lib/format/devanagari';
import { getLocale, getTranslations } from 'next-intl/server';

export const revalidate = 60;

const entryCards = [
  { key: 'dictionary', href: '/dictionary', icon: Tag, accent: 'var(--cat-keyword)' },
  { key: 'shastras', href: '/shastras', icon: BookOpen, accent: 'var(--cat-teeka)' },
  { key: 'topics', href: '/topics', icon: ScrollText, accent: 'var(--cat-topic)' },
  { key: 'graph', href: '/graph', icon: Network, accent: 'var(--cat-bhaavarth)' },
] as const;

const quickSuggestions = [
  { label: 'सम्यग्दर्शन', href: '/search?q=सम्यग्दर्शन' },
  { label: 'द्रव्य', href: '/search?q=द्रव्य' },
  { label: 'समयसार', href: '/shastras' },
  { label: 'जीव', href: '/search?q=जीव' },
];

export default async function HomePage() {
  const [counts, activity, t, locale] = await Promise.all([
    getStatsCounts(),
    getActivityRecent(),
    getTranslations('home'),
    getLocale(),
  ]);
  const isHi = locale === 'hi';
  const numerals = (n: number) =>
    isHi ? toDevanagariNumerals(n) : n.toLocaleString('en-IN');
  const countMap = {
    dictionary: counts.keywords,
    shastras: counts.shastras,
    topics: counts.topics,
    graph: counts.gathas,
  };
  const entryLabels: Record<typeof entryCards[number]['key'], { en: string; desc: string }> = {
    dictionary: { en: 'Dictionary', desc: t('entry_dictionary_desc') },
    shastras: { en: 'Shastras', desc: t('entry_shastras_desc') },
    topics: { en: 'Topics', desc: t('entry_topics_desc') },
    graph: { en: 'Graph', desc: t('entry_graph_desc') },
  };

  return (
    <div className="space-y-8">
      <section
        className="relative overflow-hidden rounded-[var(--radius-lg)] border border-border p-10 shadow-node md:p-14"
        style={{
          background:
            'radial-gradient(1200px 400px at 0% 0%, color-mix(in srgb, var(--cat-gatha-teeka) 22%, transparent) 0%, transparent 55%), radial-gradient(900px 350px at 100% 100%, color-mix(in srgb, var(--cat-topic) 14%, transparent) 0%, transparent 60%), var(--surface)',
        }}
      >
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 hidden size-72 rounded-full opacity-30 blur-3xl md:block"
          style={{ background: 'var(--cat-gatha-teeka)' }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-32 -left-20 hidden size-80 rounded-full opacity-20 blur-3xl md:block"
          style={{ background: 'var(--cat-bhaavarth)' }}
        />

        <div className="relative">
          <span
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium"
            style={{
              borderColor: 'color-mix(in srgb, var(--cat-gatha-teeka) 40%, transparent)',
              background: 'color-mix(in srgb, var(--cat-gatha-teeka) 18%, transparent)',
              color: 'var(--cat-teeka)',
            }}
          >
            <Sparkles className="size-3.5" strokeWidth={1.75} />
            {t('hero_badge')}
          </span>

          <h1 className={`${isHi ? 'font-serif-hindi font-semibold md:text-6xl' : 'font-sans font-medium tracking-tight md:text-5xl'} mt-5 text-[length:var(--font-size-display)] leading-tight text-foreground`}>
            {t('hero')}
          </h1>
          <p className={`${isHi ? 'font-sans' : 'font-serif-hindi'} mt-2 text-[length:var(--font-size-h2)] text-foreground-muted`}>
            {t('hero_sub')}
          </p>
          <p className={`${isHi ? 'font-serif-hindi' : 'font-sans'} mt-4 max-w-2xl text-[length:var(--font-size-body)] leading-relaxed text-foreground-muted`}>
            {t('hero_tagline')}
          </p>

          <form
            action="search"
            className="mt-8 flex flex-col gap-3 rounded-[var(--radius-pill)] border border-border bg-surface p-1.5 shadow-node md:flex-row md:items-center"
          >
            <div className="flex flex-1 items-center gap-2 px-4">
              <Search className="size-4 text-foreground-subtle" strokeWidth={1.75} />
              <input
                name="q"
                className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-foreground-subtle"
                placeholder={t('search_placeholder')}
              />
            </div>
            <button
              type="submit"
              className="h-11 rounded-[var(--radius-pill)] px-6 text-sm font-semibold text-white shadow-sm transition-colors"
              style={{ background: 'var(--cat-teeka)' }}
            >
              {t('search_label')}
            </button>
          </form>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-xs text-foreground-muted`}>{t('popular')}</span>
            {quickSuggestions.map((s) => (
              <Link
                key={s.label}
                href={s.href}
                className="font-serif-hindi rounded-full border border-border bg-surface px-3 py-1 text-xs text-foreground transition-colors hover:border-[color-mix(in_srgb,var(--cat-gatha-teeka)_50%,transparent)] hover:bg-[color-mix(in_srgb,var(--cat-gatha-teeka)_18%,transparent)] hover:text-[var(--cat-teeka)]"
              >
                {s.label}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-end justify-between">
          <div>
            <h2 className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-[length:var(--font-size-h2)] font-semibold`}>{t('explore_title')}</h2>
            <p className={`${isHi ? 'font-serif-hindi' : 'font-sans'} mt-1 text-sm text-foreground-muted`}>{t('explore_subtitle')}</p>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {entryCards.map((card) => {
            const Icon = card.icon;
            return (
              <Link
                key={card.key}
                href={card.href}
                className="group relative flex h-[220px] flex-col justify-between overflow-hidden rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node transition-all hover:-translate-y-0.5 hover:shadow-node-hover"
              >
                <span
                  aria-hidden
                  className="absolute inset-x-0 top-0 h-1"
                  style={{ background: card.accent }}
                />
                <div className="flex items-start justify-between">
                  <div
                    className="flex size-11 items-center justify-center rounded-[var(--radius-md)]"
                    style={{
                      background: `color-mix(in srgb, ${card.accent} 12%, transparent)`,
                      color: card.accent,
                    }}
                  >
                    <Icon className="size-5" strokeWidth={1.75} />
                  </div>
                  <span
                    className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-[length:var(--font-size-h1)] font-semibold tabular-nums`}
                    style={{ color: card.accent }}
                  >
                    {numerals(countMap[card.key])}
                  </span>
                </div>

                <div>
                  <p className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold leading-tight">
                    {t(`entry_${card.key}` as const)}
                  </p>
                  <p className="font-sans text-xs uppercase tracking-wide text-foreground-muted">
                    {entryLabels[card.key].en}
                  </p>
                  <p className={`${isHi ? 'font-serif-hindi' : 'font-sans'} mt-2 line-clamp-2 text-sm text-foreground-muted`}>
                    {entryLabels[card.key].desc}
                  </p>
                </div>

                <div className="flex items-center justify-between">
                  <span className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-xs text-foreground-muted`}>
                    {t('explore_cta')}
                  </span>
                  <span
                    className="inline-flex size-7 items-center justify-center rounded-full transition-transform group-hover:translate-x-0.5"
                    style={{
                      background: `color-mix(in srgb, ${card.accent} 12%, transparent)`,
                      color: card.accent,
                    }}
                  >
                    <ArrowRight className="size-4" strokeWidth={1.75} />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-6 shadow-node">
        <div className="flex items-end justify-between">
          <div>
            <h2 className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-[length:var(--font-size-h2)] font-semibold`}>{t('recent_activity')}</h2>
            <p className={`${isHi ? 'font-serif-hindi' : 'font-sans'} mt-1 text-sm text-foreground-muted`}>{t('recent_activity_sub')}</p>
          </div>
          <span className="inline-flex size-2 animate-pulse rounded-full" style={{ background: 'var(--cat-gatha-teeka)' }} aria-hidden />
        </div>
        <ul className="mt-5 divide-y divide-border">
          {activity.slice(0, 8).map((row) => (
            <li key={row.id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <span
                  aria-hidden
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: 'var(--cat-topic)' }}
                />
                <div className="min-w-0">
                  <p className="font-sans text-sm text-foreground">
                    {new Date(row.run_at).toLocaleString(isHi ? 'hi-IN' : 'en-IN')}
                  </p>
                  <p className={`${isHi ? 'font-serif-hindi' : 'font-sans'} truncate text-xs text-foreground-muted`}>
                    {t('activity_source')}: {row.source}
                  </p>
                </div>
              </div>
              <span
                className={`${isHi ? 'font-serif-hindi' : 'font-sans'} shrink-0 rounded-full px-3 py-1 text-sm font-semibold tabular-nums`}
                style={{
                  background: 'color-mix(in srgb, var(--cat-gatha-teeka) 22%, transparent)',
                  color: 'var(--cat-teeka)',
                }}
              >
                {numerals(row.entities_touched)}
              </span>
            </li>
          ))}
          {activity.length === 0 && (
            <li className={`${isHi ? 'font-serif-hindi' : 'font-sans'} py-6 text-center text-sm text-foreground-muted`}>
              {t('recent_empty')}
            </li>
          )}
        </ul>
      </section>
    </div>
  );
}
