"use client";

import { usePathname } from "next/navigation";

import { Nav } from "@/components/layout/nav";

export function AppFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isV1Route = pathname.startsWith("/v1");

  if (isV1Route) {
    return children;
  }

  return (
    <div className="min-h-screen px-3 py-4 md:px-5">
      <Nav />
      <main className="mx-auto max-w-7xl px-0 py-4 md:py-6">{children}</main>
    </div>
  );
}
