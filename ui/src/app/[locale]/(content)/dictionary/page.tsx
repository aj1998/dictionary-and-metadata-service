import { Link } from '@/i18n/navigation';
import { getKeywordsLetters, getKeywordsRecent } from '@/lib/api/data';
import { toDevanagariNumerals } from '@/lib/format/devanagari';

export const revalidate = 60;

export default async function DictionaryPage() {
  const [letters, recentKeywords] = await Promise.all([getKeywordsLetters(), getKeywordsRecent()]);

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold">शब्दकोश</h1>
        <div className="mt-4 grid grid-cols-4 gap-3 md:grid-cols-6 xl:grid-cols-8">
          {letters.map((entry) => (
            <Link
              key={entry.letter}
              href={`/dictionary/letters/${encodeURIComponent(entry.letter)}`}
              className="flex h-24 flex-col items-center justify-center rounded-[var(--radius-md)] border border-border bg-background transition-colors hover:bg-accent-soft"
            >
              <span className="font-serif-hindi text-[length:var(--font-size-display)] font-semibold">{entry.letter}</span>
              <span className="text-xs text-foreground-muted">{toDevanagariNumerals(entry.count)}</span>
            </Link>
          ))}
        </div>
      </section>

      <aside className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">हाल ही में जोड़े गए शब्द</h2>
        <ul className="mt-3 space-y-2">
          {recentKeywords.slice(0, 10).map((keyword) => (
            <li key={keyword.id}>
              <Link href={`/dictionary/${keyword.natural_key}`} className="block rounded-[var(--radius-sm)] border border-border px-3 py-2 text-sm hover:bg-surface-muted">
                {keyword.display_text}
              </Link>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
