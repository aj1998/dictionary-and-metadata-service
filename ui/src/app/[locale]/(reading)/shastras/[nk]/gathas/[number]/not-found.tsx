import { Link } from '@/i18n/navigation';

export default function GathaNotFound() {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-center">
      <p className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold text-foreground">
        यह गाथा उपलब्ध नहीं है
      </p>
      <p className="text-sm text-foreground-muted">
        यह गाथा क्रमांक इस शास्त्र में नहीं मिला।
      </p>
      <Link
        href="/shastras"
        className="rounded-[var(--radius-md)] border border-border bg-surface px-4 py-2 text-sm hover:border-accent hover:text-accent"
      >
        ← शास्त्र सूची पर वापस जाएँ
      </Link>
    </div>
  );
}
