import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { ApexThemeProvider } from "@/components/apex/ApexThemeProvider";

const geistSans = localFont({
  src: "../assets/fonts/Geist-Variable.woff2",
  variable: "--font-geist-sans",
  display: "swap",
});

const jetbrainsMono = localFont({
  src: "../assets/fonts/JetBrainsMono-Variable.woff2",
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Apex Health — Personal Performance Analytics",
  description:
    "A refined personal health and performance system. Monochrome analytics, tabular precision, calm confidence.",
  keywords: ["Apex Health", "health analytics", "performance", "biometrics", "training"],
  authors: [{ name: "Apex Health" }],
  icons: {
    icon: "/logo.svg",
  },
  openGraph: {
    title: "Apex Health",
    description: "Personal health & performance analytics",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${jetbrainsMono.variable} antialiased bg-canvas text-ink`}
      >
        <ApexThemeProvider>{children}</ApexThemeProvider>
        <Toaster />
      </body>
    </html>
  );
}
