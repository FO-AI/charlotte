"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import AppShell from "@/components/brand/app-shell";

export default function AccessRestrictedPage() {
  const router = useRouter();
  return (
    <AppShell>
      <section className="content-section">
        <div className="site-wrap max-w-2xl">
          <h1 className="text-navy text-3xl font-bold mb-4">Access restricted</h1>
          <p className="mb-6">
            Your UNC account is signed in, but it does not have permission for
            this page. Return home or ask your department administrator if you
            need access.
          </p>
          <Button
            onClick={() => router.push("/")}
            className="bg-navy text-white hover:bg-bolin"
          >
            Return to home
          </Button>
        </div>
      </section>
    </AppShell>
  );
}
