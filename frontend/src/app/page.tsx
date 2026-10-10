import Link from "next/link";

const FEATURES = [
  { title: "One key, many models", body: "Your users get one sk-mysite- key. Gemini and Groq keys stay on the server." },
  { title: "Smart routing", body: "Simple questions go to fast, cheap models; coding and hard questions go to stronger ones." },
  { title: "Automatic fallback", body: "If a provider fails or is overloaded, the request moves to the next one on its own." },
  { title: "Response cache", body: "Repeated questions are answered from Redis instantly, at zero cost." },
  { title: "Limits and budgets", body: "Per-key rate limits, spending caps, expiry dates and one-click revoke." },
  { title: "Usage tracking", body: "Tokens, cost and latency for every request, broken down by model." },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-5 sm:px-6">
        <span className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-7 place-items-center rounded-md bg-accent text-xs font-bold text-accent-fg">LG</span>
          LLM Gateway
        </span>
        <nav className="flex items-center gap-2 text-sm">
          <Link href="/login" className="rounded-md px-3 py-2 text-muted hover:text-foreground">
            Log in
          </Link>
          <Link href="/register" className="rounded-md bg-accent px-3.5 py-2 font-medium text-accent-fg hover:opacity-90">
            Get started
          </Link>
        </nav>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 sm:px-6">
        <section className="py-16 sm:py-24">
          <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            One OpenAI-compatible API for Gemini and Groq.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted text-pretty">
            Issue your own API keys, route each request to the right model, cache answers, and see exactly what every
            call costs.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/register" className="rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg hover:opacity-90">
              Create a free account
            </Link>
            <Link href="/login" className="rounded-md border border-border bg-surface px-4 py-2.5 text-sm font-medium hover:bg-surface-2">
              Log in
            </Link>
          </div>
        </section>

        <section className="grid gap-4 pb-20 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border border-border bg-surface p-5">
              <h2 className="text-sm font-semibold">{f.title}</h2>
              <p className="mt-1.5 text-sm text-muted">{f.body}</p>
            </div>
          ))}
        </section>
      </main>

      <footer className="border-t border-border py-6 text-center text-xs text-subtle">LLM Gateway</footer>
    </div>
  );
}
