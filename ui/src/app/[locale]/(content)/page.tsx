import { ArrowRight, BookOpen, Network, ScrollText, Tag } from '@/lib/icons';
import { Link } from '@/i18n/navigation';
import { getActivityRecent, getStatsCounts } from '@/lib/api/data';
import { toDevanagariNumerals } from '@/lib/format/devanagari';

export const revalidate = 60;

const entryCards = [
  { key: 'dictionary', titleHi: 'शब्दकोश', titleEn: 'Dictionary', href: '/dictionary', icon: Tag },
  { key: 'shastras', titleHi: 'शास्त्र', titleEn: 'Shastras', href: '/shastras', icon: BookOpen },
  { key: 'topics', titleHi: 'विषय', titleEn: 'Topics', href: '/topics', icon: ScrollText },
  { key: 'graph', titleHi: 'ग्राफ', titleEn: 'Graph', href: '/graph', icon: Network },
] as const;

export default async function HomePage() {
  const [counts, activity] = await Promise.all([getStatsCounts(), getActivityRecent()]);
  const countMap = {
    dictionary: counts.keywords,
    shastras: counts.shastras,
    topics: counts.topics,
    graph: counts.gathas,
  };

  return (
    <div className="space-y-6">
      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-8 shadow-node">
        <h1 className="font-serif-hindi text-[length:var(--font-size-display)] font-semibold text-foreground">जैन ज्ञान कोष</h1>
        <p className="mt-2 text-[length:var(--font-size-h2)] text-foreground-muted">Jain Knowledge Base</p>
        <p className="mt-3 text-[length:var(--font-size-body)] text-foreground-muted">एक संरचित ज्ञान-आधारित खोज परत</p>

        <form action="search" className="mt-6 flex flex-col gap-3 md:flex-row">
          <input
            name="q"
            className="h-11 flex-1 rounded-full border border-border bg-background px-4 text-sm"
            placeholder="गाथा, शास्त्र, कीवर्ड खोजें..."
          />
          <button
            type="submit"
            className="h-11 rounded-[var(--radius-pill)] border border-accent px-5 text-sm font-semibold text-accent"
          >
            विषय खोज
          </button>
        </form>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {entryCards.map((card) => {
          const Icon = card.icon;
          return (
            <Link
              key={card.key}
              href={card.href}
              className="group flex h-[200px] flex-col justify-between rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node transition-shadow hover:shadow-node-hover"
            >
              <Icon className="size-7 text-accent" strokeWidth={1.5} />
              <div>
                <p className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">{card.titleHi}</p>
                <p className="text-xs text-foreground-muted">{card.titleEn}</p>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold text-foreground-muted">
                  {toDevanagariNumerals(countMap[card.key])}
                </span>
                <ArrowRight className="size-4 text-accent transition-transform group-hover:translate-x-0.5" strokeWidth={1.5} />
              </div>
            </Link>
          );
        })}
      </section>

      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-6 shadow-node">
        <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">जारी प्रवृत्ति</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-foreground-muted">
              <tr>
                <th className="pb-2">समय</th>
                <th className="pb-2">स्रोत</th>
                <th className="pb-2 text-right">Entities</th>
              </tr>
            </thead>
            <tbody>
              {activity.slice(0, 10).map((row) => (
                <tr key={row.id} className="border-t border-border">
                  <td className="py-2">{new Date(row.run_at).toLocaleString('hi-IN')}</td>
                  <td className="py-2">{row.source}</td>
                  <td className="py-2 text-right font-serif-hindi">{toDevanagariNumerals(row.entities_touched)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
