import { Footer } from "@/components/Footer";

export default function ContentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    /* Centered content shell (Shell B). TopBar is in locale layout.
       max-w-[1200px] centered, 24px horizontal padding, 32px top gap. */
    <div className="flex flex-1 flex-col">
      <main className="mx-auto w-full max-w-[1200px] flex-1 px-6 pt-8 2xl:px-12">
        {children}
      </main>
      <Footer />
    </div>
  );
}
