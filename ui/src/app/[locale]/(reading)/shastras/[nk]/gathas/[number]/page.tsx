import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { GathaPanel } from '@/components/GathaPanel';
import { TaggedTermPopover } from '@/components/TaggedTermPopover';
import { Link } from '@/i18n/navigation';
import { getGatha, getGathaRelatedTopics, getGathaRelatedKeywords } from '@/lib/api/data';
import { getHindiText } from '@/lib/content-listing';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string; number: string }> };

function joinedLangText(rows: Array<{ lang: string; text: string }> | undefined): string {
  if (!rows || rows.length === 0) return '';
  return rows.map((row) => row.text).join('\n');
}

export default async function GathaDetailPage({ params }: PageProps) {
  const { nk: rawNk, number: rawNumber } = await params;
  const nk = decodeURIComponent(rawNk);
  const number = decodeURIComponent(rawNumber);

  const [gatha, topics, keywords] = await Promise.all([
    getGatha(number, { include: ['teeka_mapping'] }),
    getGathaRelatedTopics(number).catch((error) => {
      console.error('Failed to fetch gatha related topics', { nk, number, error });
      return [];
    }),
    getGathaRelatedKeywords(number).catch((error) => {
      console.error('Failed to fetch gatha related keywords', { nk, number, error });
      return [];
    }),
  ]);

  const teekaMapping = Array.isArray(gatha.teeka_mapping) ? gatha.teeka_mapping : [];
  const primaryMapping = teekaMapping[0] ?? null;

  const prakritWordMeanings = gatha.word_meanings?.prakrit?.entries ?? [];
  const prakritFullAnyavaarth = gatha.word_meanings?.prakrit?.full_anyavaarth ?? null;

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
          {prakritFullAnyavaarth && (
            <p className="mb-4 font-serif-hindi leading-8 text-foreground-muted">{prakritFullAnyavaarth}</p>
          )}
          <div className="flex flex-wrap gap-2 leading-8">
            {prakritWordMeanings.length > 0
              ? prakritWordMeanings.map((entry) => (
                  <TaggedTermPopover
                    key={`${entry.source_word[0]?.text ?? ''}-${entry.position}`}
                    termHi={entry.source_word.find((s) => s.lang === 'hi')?.text ?? entry.source_word[0]?.text ?? ''}
                    meaningHi={entry.meanings.find((m) => m.lang === 'hi')?.text ?? entry.meanings[0]?.text ?? ''}
                  />
                ))
              : (joinedLangText(gatha.prakrit?.text) || '').split(/\s+/).filter(Boolean).slice(0, 40).map((token, index) => (
                  <TaggedTermPopover key={`${token}-${index}`} termHi={token} meaningHi={token} />
                ))}
          </div>
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">टीका</h2>
          {primaryMapping ? (
            <div className="space-y-4">
              {primaryMapping.full_anyavaarth && (
                <p className="font-serif-hindi leading-8 text-foreground-muted">{primaryMapping.full_anyavaarth}</p>
              )}
              {primaryMapping.tagged_terms.length > 0 && (
                <div className="flex flex-wrap gap-2 leading-8">
                  {primaryMapping.tagged_terms.map((term, index) => (
                    <TaggedTermPopover
                      key={`${term.source_word}-${index}`}
                      termHi={term.source_word}
                      meaningHi={term.meaning}
                    />
                  ))}
                </div>
              )}
              {primaryMapping.anvayartha.length > 0 && (
                <p className="whitespace-pre-wrap font-serif-hindi leading-8">
                  {joinedLangText(primaryMapping.anvayartha)}
                </p>
              )}
              {primaryMapping.is_related.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="text-sm text-foreground-muted">संबंधित गाथाएँ:</span>
                  {primaryMapping.is_related.map((relatedNumber) => (
                    <Link
                      key={relatedNumber}
                      href={`/shastras/${nk}/gathas/${relatedNumber}`}
                      className="rounded-full bg-accent-soft px-3 py-1 text-xs text-accent"
                    >
                      {relatedNumber}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p>टीका उपलब्ध नहीं है।</p>
          )}
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
