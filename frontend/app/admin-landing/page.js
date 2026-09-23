'use client';

import ProtectedRoute from "@/components/protected-route";
import AdminLanding from "@/components/admin-landing";
import AppShell from "@/components/brand/app-shell";

export default function AdminLandingPage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <AdminLanding />
      </AppShell>
    </ProtectedRoute>
  );
}
