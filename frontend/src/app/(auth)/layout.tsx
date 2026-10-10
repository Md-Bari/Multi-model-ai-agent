import Link from "next/link";
import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-12">
      <Link href="/" className="mb-8 flex items-center gap-2 font-semibold tracking-tight">
        <span className="grid size-7 place-items-center rounded-md bg-accent text-xs font-bold text-accent-fg">LG</span>
        LLM Gateway
      </Link>
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-sm">{children}</div>
    </div>
  );
}
