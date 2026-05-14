import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { GathaPanel } from '@/components/GathaPanel';
import { TaggedTermPopover } from '@/components/TaggedTermPopover';
import { Link } from '@/i18n/navigation';
import { getGatha, getGathaRelatedTopics, getGathaRelatedKeywords } from '@/lib/api/data';
import { getHindiText } from '@/lib/content-listing';
import { splitTeekaByBracketTerms } from '@/lib/gatha-content';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string; number: string }> };

function joinedLangText(rows: Array<{ lang: string; text: string }> | undefined): string {
  if (!rows || rows.length === 0) return '';
  return rows.map((row) => row.text).join('\n');
}

export default async function GathaDetailPage({ params }: PageProps) {
  const { nk, number } = await params;

  const [gatha, topics, keywords] = await Promise.all([
    getGatha(number),
    getGathaRelatedTopics(number).catch((error) => {
      console.error('Failed to fetch gatha related topics', { nk, number, error });
      return [];
    }),
    getGathaRelatedKeywords(number).catch((error) => {
      console.error('Failed to fetch gatha related keywords', { nk, number, error });
      return [];
    }),
  ]);

  const teekaText = typeof gatha.teeka_mapping === 'string' ? gatha.teeka_mapping : '';
  const teekaParts = splitTeekaByBracketTerms(teekaText);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <BreadcrumbBar
            segments={[
              { label: 'शास्त्र', href: '/shastras' },
              { label: nk, href: `/shastras/${nk}` },
              { label: `गाथा ${gatha.gatha_number || number}` },
            ]}
          />
        </section>

        <GathaPanel lang="prakrit" text={joinedLangText(gatha.prakrit?.text) || '—'} />
        {gatha.sanskrit && <GathaPanel lang="sanskrit" text={joinedLangText(gatha.sanskrit.text)} />}
        <GathaPanel lang="hindi-harigeet" text={joinedLangText(gatha.hindi_chhand[0]?.text) || '—'} />

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">शब्दार्थ</h2>
          <div className="flex flex-wrap gap-2 leading-8">
            {(joinedLangText(gatha.prakrit?.text) || '').split(/\s+/).filter(Boolean).slice(0, 40).map((token, index) => (
              <TaggedTermPopover key={`${token}-${index}`} termHi={token} meaningHi={token} />
            ))}
          </div>
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">टीका</h2>
          <p className="whitespace-pre-wrap leading-8">
            {teekaParts.length === 0
              ? 'टीका उपलब्ध नहीं है।'
              : teekaParts.map((part, index) =>
                  part.type === 'term' ? (
                    <TaggedTermPopover key={`${part.value}-${index}`} termHi={part.value} meaningHi={part.value} />
                  ) : (
                    <span key={`text-${index}`}>{part.value}</span>
                  ))}
          </p>
        </section>
      </div>

      <aside className="space-y-4 lg:sticky lg:top-[90px] lg:self-start">
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <h3 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">संबंधित विषय</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            {topics.slice(0, 12).map((topic) => (
              <Link key={topic.id} href={`/topics/${topic.natural_key}`} className="rounded-full bg-accent-soft px-3 py-1 text-xs text-accent">
                {getHindiText(topic.display_text, topic.natural_key)}
              </Link>
            ))}
          </div>
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <h3 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">संबंधित कीवर्ड</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            {keywords.slice(0, 12).map((keyword) => (
              <Link key={keyword.id} href={`/dictionary/${keyword.natural_key}`} className="rounded-full bg-surface-muted px-3 py-1 text-xs">
                {keyword.display_text}
              </Link>
            ))}
          </div>
        </section>

        <Link href={`/graph?node=${encodeURIComponent(`gatha:${gatha.natural_key}`)}`} className="block rounded-[var(--radius-md)] bg-accent p-4 text-center font-semibold text-white shadow-node">
          ग्राफ में खोलें
        </Link>
      </aside>
    </div>
  );
}
