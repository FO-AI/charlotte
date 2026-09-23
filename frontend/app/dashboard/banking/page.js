'use client';

import ProtectedRoute from "@/components/protected-route";
import BankingDashboard from "@/components/banking/dashboard";
import AccessRestrictedPage from "@/app/access-restricted/page";
import { useAuth } from "@/lib/auth/auth-context-msal";
import AppShell from "@/components/brand/app-shell";

export default function BankingDashboardPage() {
  const { isBanking, isAdmin } = useAuth();
  if (!isBanking && !isAdmin) {
    return <AccessRestrictedPage />;
  }
  return (
    <ProtectedRoute>
      <AppShell>
        <BankingDashboard />
      </AppShell>
    </ProtectedRoute>
  );
}
