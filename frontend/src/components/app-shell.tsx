"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { ApiError, api, post } from "@/lib/api";
import type { User } from "@/lib/types";

import { Button, Skeleton, cn } from "./ui";

const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/keys", label: "API keys" },
  { href: "/playground", label: "Playground" },
  { href: "/docs", label: "Docs" },
];

/** Verifies the session with the backend, then renders the signed-in layout. */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  const toLogin = useCallback(() => router.replace(`/login?next=${encodeURIComponent(pathname)}`), [router, pathname]);

  useEffect(() => {
    let active = true;
    api<User>("/auth/me")
      .then((u) => active && setUser(u))
      .catch((e) => {
        if (!active) return;
        if (e instanceof ApiError && e.status === 401) toLogin();
        else setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [toLogin]);

  async function logout() {
    await post("/auth/logout").catch(() => undefined);
    router.replace("/login");
  }

  if (!user) {
    return (
      <div className="mx-auto w-full max-w-6xl p-6">
        {error ? (
          <div className="rounded-xl border border-border bg-surface p-6 text-sm">
            <p className="font-medium text-foreground">Couldn&apos;t load your account</p>
            <p className="mt-1 text-muted">{error}</p>
            <Button className="mt-4" variant="secondary" onClick={() => location.reload()}>
              Retry
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        )}
      </div>
    );
  }

  return (
    <UserContext.Provider value={user}>
      <div className="flex min-h-screen w-full flex-col md:flex-row">
        <aside className="border-b border-border bg-surface md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-r md:border-b-0">
          <div className="flex items-center justify-between px-5 py-4">
            <Link href="/dashboard" className="flex items-center gap-2 font-semibold tracking-tight text-foreground">
              <span className="grid size-7 place-items-center rounded-md bg-accent text-xs font-bold text-accent-fg">LG</span>
              LLM Gateway
            </Link>
            <button className="text-sm text-muted md:hidden" onClick={() => setMenuOpen((o) => !o)} aria-expanded={menuOpen}>
              Menu
            </button>
          </div>
          <nav className={cn("flex-col gap-0.5 px-3 pb-3 md:flex", menuOpen ? "flex" : "hidden")}>
            {NAV.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className={cn(
                    "rounded-md px-3 py-2 text-sm transition",
                    active ? "bg-surface-2 font-medium text-foreground" : "text-muted hover:bg-surface-2 hover:text-foreground",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
            <div className="mt-4 border-t border-border px-3 pt-4 md:mt-auto">
              <p className="truncate text-xs text-subtle" title={user.email}>
                {user.email}
              </p>
              <Button variant="ghost" className="mt-2 -ml-3.5" onClick={logout}>
                Log out
              </Button>
            </div>
          </nav>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </UserContext.Provider>
  );
}
