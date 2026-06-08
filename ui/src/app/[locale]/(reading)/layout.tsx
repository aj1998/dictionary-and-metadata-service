import { Footer } from "@/components/Footer";

export default function ReadingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    /* Reading shell (Shell C). TopBar is in locale layout.
       Pages manage their own column layout. */
    <div className="flex flex-1 flex-col">
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 pt-8 2xl:px-12">
        {children}
      </main>
      <Footer />
    </div>
  );
}
