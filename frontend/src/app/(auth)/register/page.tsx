import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Create account" };

export default function RegisterPage() {
  return (
    <>
      <h1 className="mb-1 text-lg font-semibold">Create your account</h1>
      <p className="mb-6 text-sm text-muted">Free. You&apos;ll be able to create API keys right away.</p>
      <Suspense>
        <AuthForm mode="register" />
      </Suspense>
    </>
  );
}
