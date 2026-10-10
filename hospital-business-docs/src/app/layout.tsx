import type { Metadata } from "next";
import { Geist, JetBrains_Mono } from "next/font/google";
import { RootProvider } from "fumadocs-ui/provider/next";
import { defineTranslations } from "fumadocs-core/i18n";
import { i18nProvider, uiTranslations } from "fumadocs-ui/i18n";
import "./globals.css";

const idTranslations = defineTranslations().extend(uiTranslations()).add({
  "Ask AI(AI chat button)": "Tanya AI",
  "Back to Home(404 page)": "Kembali ke Beranda",
  "Choose a language(language switcher)": "Pilih bahasa",
  "Choose a language(language switcher)(aria-label)": "Pilih bahasa",
  "Close Banner(banner)(aria-label)": "Tutup banner",
  "Close Search(search dialog)(aria-label)": "Tutup pencarian",
  "Close Sidebar(aria-label)": "Tutup sidebar",
  "Close Sidebar(sidebar)(aria-label)": "Tutup sidebar",
  "Collapse Sidebar(sidebar)(aria-label)": "Ciutkan sidebar",
  "Copied Anchor Link(heading anchor)(aria-label)": "Tautan heading disalin",
  "Copied Link(accordion)(aria-label)": "Tautan disalin",
  "Copied Markdown(page actions)": "Markdown disalin",
  "Copied Text(code block)(aria-label)": "Teks disalin",
  "Copy Anchor Link(heading anchor)(aria-label)": "Salin tautan heading",
  "Copy Link(accordion)(aria-label)": "Salin tautan",
  "Copy Markdown(page actions)": "Salin Markdown",
  "Copy Text(code block)(aria-label)": "Salin teks",
  "Dark(theme switcher)(aria-label)": "Tema gelap",
  "Default(type table)": "Default",
  "Hide Sidebar(sidebar)": "Sembunyikan sidebar",
  "Layout Tab(layout tab trigger)": "Tab tata letak",
  "Light(theme switcher)(aria-label)": "Tema terang",
  "Next Page(pagination)": "Halaman berikutnya",
  "No Headings(table of contents)": "Tidak ada heading",
  "No results found(search dialog)": "Tidak ada hasil. Coba kata kunci lain.",
  "On this page(table of contents)": "Di halaman ini",
  "Open Search(search trigger)(aria-label)": "Buka pencarian",
  "Open Sidebar(sidebar)(aria-label)": "Buka sidebar",
  "Open in ChatGPT(page actions)": "Buka di ChatGPT",
  "Open in Claude(page actions)": "Buka di Claude",
  "Open in Cursor(page actions)": "Buka di Cursor",
  "Open in Scira AI(page actions)": "Buka di Scira AI",
  "Open(page actions)": "Buka",
  "Page Not Found(404 page)": "Halaman Tidak Ditemukan",
  "Parameters(type table)": "Parameter",
  "Previous Page(pagination)": "Halaman sebelumnya",
  "Prop(type table)": "Properti",
  "Read {url}, I want to ask questions about it.(page actions)":
    "Baca {url}, saya ingin bertanya tentang halaman ini.",
  "Returns(type table)": "Nilai yang dikembalikan",
  "Search(search dialog)": "Cari dokumentasi",
  "Search(search trigger)": "Cari",
  "Show Sidebar(sidebar)": "Tampilkan sidebar",
  "System(theme switcher)(aria-label)": "Tema sistem",
  "Table of Contents(inline table of contents)": "Daftar Isi",
  "The page you are looking for might have been removed, had its name changed, or is temporarily unavailable.(404 page)":
    "Halaman yang Anda cari mungkin telah dihapus, namanya diubah, atau untuk sementara tidak tersedia.",
  "Toggle Menu(mobile menu)(aria-label)": "Buka atau tutup menu",
  "Toggle Theme(theme switcher)(aria-label)": "Ganti tema",
  "Type(type table)": "Tipe",
  "View as Markdown(page actions)": "Lihat sebagai Markdown",
  displayName: "Bahasa Indonesia",
});
const geist = Geist({
  variable: "--font-geist",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Hospital Business Process — Mayapada",
    template: "%s | Hospital BP Mayapada",
  },
  description: "Basis pengetahuan proses bisnis rumah sakit Indonesia dan pemetaannya ke kode Odoo Mayapada.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="id"
      className={`${geist.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-screen flex-col">
        <RootProvider
          search={{ preload: true, options: { api: "/api/search" } }}
          i18n={i18nProvider(idTranslations)}
        >
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
