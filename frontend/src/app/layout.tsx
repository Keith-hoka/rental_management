import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { InlineScript } from "@/components/inline-script";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Rental Management",
  description: "Manage properties, leases, rent and maintenance in one place.",
};

export const viewport: Viewport = {
  colorScheme: "light dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      // The inline script sets data-theme here before React hydrates.
      suppressHydrationWarning
    >
      <head>
        {/* Stamps the stored theme before first paint, so a dark-mode user never
            sees the page render light and flip once React hydrates. No default
            attribute: its absence is what lets the media query follow the OS. */}
        <InlineScript
          html={`try{var t=localStorage.getItem("theme");if(t==="dark"||t==="light"){document.documentElement.dataset.theme=t}}catch(e){}`}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
