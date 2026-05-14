export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center">
      <div className="text-center">
        <h1 className="text-[length:var(--font-size-display)] font-semibold" style={{ color: "var(--foreground)" }}>
          जैन ज्ञान कोष
        </h1>
        <p className="mt-2 text-[length:var(--font-size-h2)]" style={{ color: "var(--foreground-muted)" }}>
          Jain Knowledge Base
        </p>
        <div className="mt-8 inline-block rounded-[var(--radius-md)] px-6 py-3 text-white font-semibold" style={{ background: "var(--accent)" }}>
          Phase 0 — Bootstrap complete
        </div>
      </div>
    </main>
  );
}
