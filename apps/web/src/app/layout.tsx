import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "@xterm/xterm/css/xterm.css";
import "./globals.css";
import { Telemetry } from "@/components/telemetry";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Agentic SDLC Workbench",
  description: "A governed, observable environment for agentic software delivery",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-[#080b11] text-slate-100">
        <Telemetry />
        {children}
      </body>
    </html>
  );
}
