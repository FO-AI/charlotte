'use client';

import ProtectedRoute from "@/components/protected-route";
import Dashboard from "@/components/accounting/dashboard";
import AccessRestrictedPage from "@/app/access-restricted/page";
import { useAuth } from "@/lib/auth/auth-context-msal";
import AppShell from "@/components/brand/app-shell";

export default function DashboardPage() {
  const { isAccounting, isAdmin } = useAuth();
  if (!isAccounting && !isAdmin) {
    return <AccessRestrictedPage />;
  }
  return (
    <ProtectedRoute>
      <AppShell>
        <Dashboard />
      </AppShell>
    </ProtectedRoute>
  );
}
