export default function HomePage() {
  return (
    <div className="rounded-[var(--radius-md)] border border-border bg-surface p-8 shadow-node">
      <h1 className="font-serif-hindi text-[length:var(--font-size-display)] font-semibold text-foreground">
        जैन ज्ञान कोष
      </h1>
      <p className="mt-2 text-[length:var(--font-size-h2)] text-foreground-muted">
        Jain Knowledge Base
      </p>
      <div
        className="mt-8 inline-block rounded-[var(--radius-md)] px-6 py-3 font-semibold text-white"
        style={{ background: "var(--accent)" }}
      >
        Phase 1 — Shell loaded
      </div>
    </div>
  );
}
