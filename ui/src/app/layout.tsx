import type { Metadata } from "next";
import { Noto_Serif_Devanagari, Inter } from "next/font/google";
import { getLocale } from "next-intl/server";
import "./globals.css";

const notoSerifDevanagari = Noto_Serif_Devanagari({
  variable: "--font-serif-hindi",
  subsets: ["devanagari"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: true,
  fallback: ["Mangal", "Devanagari MT", "serif"],
});

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "जैन ज्ञान कोष (Jain Knowledge Base)",
  description:
    "Jain scripture knowledge base — graph-driven exploration of Shastras, Gathas, Topics and Keywords.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();

  return (
    <html
      lang={locale}
      className={`${notoSerifDevanagari.variable} ${inter.variable} h-full`}
    >
      <body className="flex min-h-full flex-col antialiased">
        {children}
      </body>
    </html>
  );
}
