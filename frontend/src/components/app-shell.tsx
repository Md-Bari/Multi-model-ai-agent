"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { AUTH_EXPIRED_EVENT, ApiError, api, post } from "@/lib/api";
import type { User } from "@/lib/types";

import { Button, Skeleton, cn } from "./ui";

const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/usage", label: "Usage" },
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
    // Any API call that gets a 401 later (session expired) sends the user to login.
    window.addEventListener(AUTH_EXPIRED_EVENT, toLogin);
    return () => {
      active = false;
      window.removeEventListener(AUTH_EXPIRED_EVENT, toLogin);
    };
  }, [toLogin]);

  async function logout() {
    await post("/auth/logout").catch(() => undefined);
    router.replace("/login");
  }

  // The layout and page render immediately (instant navigation); only the account
  // details wait for /auth/me. proxy.ts already keeps signed-out visitors out.
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
              {user ? (
                <p className="truncate text-xs text-subtle" title={user.email}>
                  {user.email}
                </p>
              ) : (
                <Skeleton className="h-4 w-32" />
              )}
              <Button variant="ghost" className="mt-2 -ml-3.5" onClick={logout}>
                Log out
              </Button>
            </div>
          </nav>
        </aside>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <div className="mx-auto max-w-6xl">
            {error && (
              <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface p-4 text-sm">
                <span>
                  <span className="font-medium text-foreground">Couldn&apos;t reach your account.</span>{" "}
                  <span className="text-muted">{error}</span>
                </span>
                <Button variant="secondary" onClick={() => location.reload()}>
                  Retry
                </Button>
              </div>
            )}
            {children}
          </div>
        </main>
      </div>
    </UserContext.Provider>
  );
}
