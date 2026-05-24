import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { GathaPanel } from '@/components/GathaPanel';
import { TaggedTermPopover } from '@/components/TaggedTermPopover';
import { Link } from '@/i18n/navigation';
import { getKalash, getKalashWordMeanings } from '@/lib/api/data';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string; number: string }> };

function joinedLangText(rows: Array<{ lang: string; text: string }> | undefined): string {
  if (!rows || rows.length === 0) return '';
  return rows.map((row) => row.text).join('\n');
}

export default async function KalashDetailPage({ params }: PageProps) {
  const { nk: rawNk, number: rawNumber } = await params;
  const nk = decodeURIComponent(rawNk);
  const number = decodeURIComponent(rawNumber);

  const kalashNk = `${nk}:amritchandra:kalash:${number}`;

  const [kalash, wordMeanings] = await Promise.all([
    getKalash(kalashNk),
    getKalashWordMeanings(kalashNk),
  ]);

  const shastraTitle = joinedLangText(kalash.teeka.shastra.title) || nk;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <BreadcrumbBar
            segments={[
              { label: 'शास्त्र', href: '/shastras' },
              { label: shastraTitle, href: `/shastras/${nk}` },
              { label: `कलश ${kalash.kalash_number || number}` },
            ]}
          />
        </section>

        {kalash.sanskrit && (
          <GathaPanel lang="sanskrit" text={joinedLangText(kalash.sanskrit.text) || '—'} />
        )}
        {kalash.hindi && (
          <GathaPanel lang="hindi-harigeet" text={joinedLangText(kalash.hindi.text) || '—'} />
        )}

        {wordMeanings && wordMeanings.entries.length > 0 && (
          <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
            <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">शब्दार्थ</h2>
            <div className="flex flex-wrap gap-2 leading-8">
              {wordMeanings.entries.map((entry) => (
                <TaggedTermPopover
                  key={`${entry.source_word}-${entry.position}`}
                  termHi={entry.source_word}
                  meaningHi={entry.meaning}
                />
              ))}
            </div>
          </section>
        )}

        {kalash.bhaavarth.length > 0 && (
          <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
            <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">भावार्थ</h2>
            {kalash.bhaavarth.map((b) => (
              <p key={b.natural_key} className="whitespace-pre-wrap font-serif-hindi leading-8">
                {joinedLangText(b.text)}
              </p>
            ))}
          </section>
        )}
      </div>

      <aside className="space-y-4 lg:sticky lg:top-[90px] lg:self-start">
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <h3 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">टीका</h3>
          <p className="mt-2 text-sm text-foreground-muted">
            {kalash.teeka.teekakar?.display_name.find((d) => d.lang === 'hi')?.text
              ?? kalash.teeka.natural_key}
          </p>
        </section>

        <Link
          href={`/graph?node=${encodeURIComponent(`kalash:${kalash.natural_key}`)}`}
          className="block rounded-[var(--radius-md)] bg-accent p-4 text-center font-semibold text-white shadow-node"
        >
          ग्राफ में खोलें
        </Link>
      </aside>
    </div>
  );
}
