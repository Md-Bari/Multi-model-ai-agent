import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <>
      <h1 className="mb-1 text-lg font-semibold">Welcome back</h1>
      <p className="mb-6 text-sm text-muted">Log in to manage your keys and usage.</p>
      {/* useSearchParams (for ?next=) needs a Suspense boundary on prerendered pages */}
      <Suspense>
        <AuthForm mode="login" />
      </Suspense>
    </>
  );
}
