import { getLocale, getTranslations } from 'next-intl/server';

export default async function AboutPage() {
  const [t, locale] = await Promise.all([getTranslations('about'), getLocale()]);
  const isHi = locale === 'hi';
  const fontBody = isHi ? 'font-serif-hindi' : 'font-sans';
  return (
    <div className="max-w-[720px] mx-auto space-y-6">
      {/* Mission */}
      <div className="rounded-[var(--radius-md)] border border-border bg-surface p-8 shadow-node">
        <h1 className={`${fontBody} text-[length:var(--font-size-h1)] font-semibold text-foreground`}>
          {t('title')}
        </h1>
        <div className={`mt-4 space-y-4 ${fontBody} text-[length:var(--font-size-body)] leading-relaxed text-foreground`}>
          <p>{t('p1')}</p>
          <p>{t('p2')}</p>
          <p>{t('p3')}</p>
        </div>
      </div>

      {/* Sources */}
      <div className="rounded-[var(--radius-md)] border border-border bg-surface p-8 shadow-node">
        <h2 className={`${fontBody} text-[length:var(--font-size-h2)] font-semibold text-foreground`}>
          {t('sources_heading')}
        </h2>
        <div className="mt-4 space-y-4">
          {/* Source 1 */}
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-4">
            <p className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold text-foreground">
              जैनकोश
            </p>
            <a
              href="https://jainkosh.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-accent hover:underline"
            >
              jainkosh.org
            </a>
            <p className="mt-1 text-sm text-foreground-muted">Creative Commons license</p>
          </div>

          {/* Source 2 */}
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-4">
            <p className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold text-foreground">
              Nikky Jain Agam
            </p>
            <a
              href="https://nikkyjain.github.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-accent hover:underline"
            >
              nikkyjain.github.io
            </a>
            <p className="mt-1 text-sm text-foreground-muted">Open source</p>
          </div>

          {/* Source 3 */}
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-4">
            <p className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold text-foreground">
              व्याकरण विश्लेषण
            </p>
            <p className="text-sm text-foreground-muted">Vyakaran Vishleshan</p>
            <p className="mt-1 text-sm text-foreground-muted">Original research corpus</p>
          </div>
        </div>
      </div>

      {/* Tech stack */}
      <div className="rounded-[var(--radius-md)] border border-border bg-surface px-8 py-6 shadow-node">
        <p className={`${fontBody} text-sm font-medium text-foreground-muted`}>{t('tech_stack')}</p>
        <p className="mt-2 text-sm text-foreground-muted">
          FastAPI · PostgreSQL · MongoDB · Neo4j · Next.js 16 · Tailwind 4
        </p>
      </div>
    </div>
  );
}
