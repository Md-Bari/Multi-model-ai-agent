"use client";

import { useState } from "react";

import { Card, PageHeader, cn } from "@/components/ui";
import { PUBLIC_API_URL } from "@/lib/api";

const EXAMPLES = {
  curl: `curl ${PUBLIC_API_URL}/v1/chat/completions \\
  -H "Authorization: Bearer $GATEWAY_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Hello!"}]}'`,
  python: `# pip install openai
import os
from openai import OpenAI

client = OpenAI(base_url="${PUBLIC_API_URL}/v1", api_key=os.environ["GATEWAY_KEY"])

stream = client.chat.completions.create(
    model="auto",  # or "cheap" / "strong"
    messages=[{"role": "user", "content": "Explain recursion in one paragraph"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")`,
  javascript: `// npm install openai  (run this on your server, never in the browser)
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "${PUBLIC_API_URL}/v1", apiKey: process.env.GATEWAY_KEY });

const res = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(res.choices[0].message.content);`,
  langchain: `# pip install langchain-openai
import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(base_url="${PUBLIC_API_URL}/v1", api_key=os.environ["GATEWAY_KEY"], model="auto")
print(llm.invoke("Hello!").content)`,
};

type Lang = keyof typeof EXAMPLES;

const ERRORS = [
  ["401", "Missing, invalid, revoked or expired key"],
  ["402", "The key's budget is used up"],
  ["429", "Rate limit exceeded (see the Retry-After header)"],
  ["502", "Every provider failed for this request"],
  ["503", "No provider is configured on the server"],
];

export default function DocsPage() {
  const [lang, setLang] = useState<Lang>("curl");

  return (
    <>
      <PageHeader title="Docs" description="The gateway speaks the OpenAI Chat Completions format, so existing SDKs work unchanged." />

      <div className="space-y-6">
        <Card title="Quick start">
          <div className="mb-3 flex flex-wrap gap-1" role="tablist">
            {(Object.keys(EXAMPLES) as Lang[]).map((l) => (
              <button
                key={l}
                role="tab"
                aria-selected={lang === l}
                onClick={() => setLang(l)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm capitalize transition",
                  lang === l ? "bg-surface-2 font-medium text-foreground" : "text-muted hover:text-foreground",
                )}
              >
                {l}
              </button>
            ))}
          </div>
          <pre className="overflow-x-auto rounded-lg bg-surface-2 p-4 font-mono text-xs leading-relaxed">{EXAMPLES[lang]}</pre>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Models">
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="font-mono text-xs font-medium">auto</dt>
                <dd className="text-muted">The gateway decides from the prompt: simple questions go to the fast tier; coding and hard questions to the strong tier.</dd>
              </div>
              <div>
                <dt className="font-mono text-xs font-medium">cheap</dt>
                <dd className="text-muted">Always the fast, low-cost tier.</dd>
              </div>
              <div>
                <dt className="font-mono text-xs font-medium">strong</dt>
                <dd className="text-muted">Always the strongest configured model.</dd>
              </div>
            </dl>
            <p className="mt-4 text-xs text-subtle">
              Response headers show what happened: <code>X-Gateway-Tier</code>, <code>X-Gateway-Model</code>,{" "}
              <code>X-Gateway-Cache</code>.
            </p>
          </Card>

          <Card title="Errors">
            <table className="w-full text-sm">
              <tbody>
                {ERRORS.map(([code, text]) => (
                  <tr key={code} className="border-b border-border last:border-0">
                    <td className="py-2 pr-4 font-mono text-xs">{code}</td>
                    <td className="py-2 text-muted">{text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>

        <Card title="Interactive API reference">
          <p className="text-sm text-muted">
            Swagger UI with every endpoint:{" "}
            <a href={`${PUBLIC_API_URL}/docs`} target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline">
              {PUBLIC_API_URL}/docs
            </a>
          </p>
        </Card>
      </div>
    </>
  );
}
