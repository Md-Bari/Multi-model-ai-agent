"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { post } from "@/lib/api";
import type { User } from "@/lib/types";

import { Button, ErrorText, Field, Input } from "./ui";

/** Only allow redirects to paths on this site. */
function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const isLogin = mode === "login";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await post<User>(isLogin ? "/auth/login" : "/auth/register", { email, password });
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <Field label="Email">
        <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Password" hint={isLogin ? undefined : "At least 8 characters"}>
        <Input
          type="password"
          autoComplete={isLogin ? "current-password" : "new-password"}
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <ErrorText>{error}</ErrorText>
      <Button type="submit" loading={loading} className="mt-1 w-full">
        {isLogin ? "Log in" : "Create account"}
      </Button>
      <p className="text-center text-sm text-muted">
        {isLogin ? "No account yet? " : "Already have an account? "}
        <Link href={isLogin ? "/register" : "/login"} className="font-medium text-accent hover:underline">
          {isLogin ? "Create one" : "Log in"}
        </Link>
      </p>
    </form>
  );
}
