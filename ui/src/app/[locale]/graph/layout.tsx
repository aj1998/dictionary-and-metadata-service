export default function GraphLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    /* Full-bleed three-pane shell. TopBar is in locale layout.
       Left pane: hidden at <xl, fixed 280px at xl+.
       Right pane: hidden (details panel — wired in Phase 5).
       Center: flex-1 full-bleed canvas. */
    <div className="flex flex-1 overflow-hidden">
      {/* Left filter pane */}
      <aside
        className="hidden xl:flex w-[280px] shrink-0 flex-col overflow-y-auto border-r border-border bg-surface"
        aria-label="फ़िल्टर"
      >
        {/* Phase 4: CategoryFilterList */}
      </aside>

      {/* Center canvas */}
      <main className="relative flex-1 overflow-hidden">
        {children}
      </main>

      {/* Right details pane — hidden until Phase 5 wires it up */}
      {/* Phase 5: DetailsPanel */}
    </div>
  );
}
