import { Footer } from "@/components/Footer";

export default function ReadingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    /* Split-reading shell (Shell C). TopBar is in root layout.
       65% reader column + 35% sticky sidebar.
       Stacks to single column at <1024px. */
    <div className="flex flex-1 flex-col">
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 pt-8 2xl:px-12">
        <div className="flex flex-col gap-8 lg:flex-row">
          {/* Reader column */}
          <div className="min-w-0 flex-1 lg:basis-[65%]">
            {children}
          </div>

          {/* Sidebar slot — populated by individual reading pages */}
          <aside
            id="reading-sidebar"
            className="w-full shrink-0 lg:sticky lg:top-[calc(4rem+1px)] lg:h-[calc(100vh-4rem-1px)] lg:w-[35%] lg:overflow-y-auto"
          />
        </div>
      </main>
      <Footer />
    </div>
  );
}
