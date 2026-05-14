import { Link } from '@/i18n/navigation';
import { Loader2 } from '@/lib/icons';
import { searchTopics } from '@/lib/api/query';

export const revalidate = 0;

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

export default async function SearchPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const q = first(query.q).trim();

  let errorMessage = '';
  let results: Awaited<ReturnType<typeof searchTopics>>['results'] = [];

  if (q) {
    try {
      const response = await searchTopics({ q, caller: 'public-ui' });
      results = response.results;
    } catch (error) {
      console.error('Search query failed', error);
      errorMessage = 'खोज सेवा अस्थायी रूप से उपलब्ध नहीं है';
    }
  }

  return (
    <div className="rounded-[var(--radius-md)] border border-border bg-surface p-6 shadow-node">
      <form className="mx-auto flex max-w-3xl gap-3">
        <input
          autoFocus
          name="q"
          defaultValue={q}
          placeholder='कीवर्ड लिखें जैसे "पर्याय गुण भेद"'
          className="h-14 flex-1 rounded-full border border-border bg-background px-5 text-base"
        />
        <button type="submit" className="inline-flex h-14 items-center justify-center rounded-full bg-accent px-6 font-semibold text-white">
          खोजें
        </button>
      </form>

      {errorMessage && <p className="mt-4 rounded border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{errorMessage}</p>}

      {!q && (
        <div className="mt-8 flex items-center justify-center gap-2 text-sm text-foreground-muted">
          <Loader2 className="size-4 animate-spin" strokeWidth={1.5} />
          खोज शुरू करने के लिए कोई कीवर्ड लिखें
        </div>
      )}

      {q && results.length === 0 && !errorMessage && (
        <p className="mt-8 text-center text-sm text-foreground-muted">कोई परिणाम नहीं मिला</p>
      )}

      <div className="mt-6 space-y-3">
        {results.map((result, index) => (
          <article key={`${result.topic_nk}-${index}`} className="rounded-[var(--radius-md)] border border-border bg-background p-4">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">
                {index + 1}. {result.title_hi}
              </h2>
              <span className="rounded-full bg-accent-soft px-2 py-1 text-xs text-accent">overlap {result.overlap.matched}/{result.overlap.total} • score {result.score.toFixed(1)}</span>
            </div>
            <p className="mt-2 text-sm text-foreground-muted">matched: {result.matched_tokens.join(', ')}</p>
            <p className="mt-2 text-sm">{result.excerpt}</p>
            <p className="mt-2 text-xs text-foreground-muted">mentions: {result.mentions.map((m) => `${m.kind}:${m.ref}`).join(' • ')}</p>
            <div className="mt-3 flex gap-4 text-sm">
              <Link href={`/topics/${result.topic_nk}`} className="font-medium text-accent">विषय खोलें →</Link>
              <Link href={`/graph?node=${encodeURIComponent(result.topic_nk)}`} className="font-medium text-accent">ग्राफ में खोलें →</Link>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
