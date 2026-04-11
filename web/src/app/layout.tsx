import type { Metadata } from "next";
import { Fraunces, Manrope } from "next/font/google";

import { AppFrame } from "@/components/layout/app-frame";
import { Providers } from "@/components/layout/providers";

import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-serif-display",
});

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-sans-body",
});

export const metadata: Metadata = {
  title: "Shopper",
  description: "Phase 3 frontend for the AI meal planner and grocery shopping agent.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${fraunces.variable} ${manrope.variable} min-h-screen`}>
        <Providers>
          <AppFrame>{children}</AppFrame>
        </Providers>
      </body>
    </html>
  );
}
