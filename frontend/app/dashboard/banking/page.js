/*
This is the banking dashboard page for the application
The dashboard page will be the main page for banking team users
It will have an aesthetic design matching the accounting dashboard
*/

'use client';

import ProtectedRoute from "@/components/protected-route";
import BankingDashboard from "@/components/banking/dashboard";
import AccessRestrictedPage from "@/app/access-restricted/page";
import { useAuth } from "@/lib/auth/auth-context-msal";

export default function BankingDashboardPage() {
  const { isBanking, isAdmin } = useAuth();
  if (!isBanking && !isAdmin) {
    return <AccessRestrictedPage />;
  }
  return (
    <ProtectedRoute>
      <BankingDashboard />
    </ProtectedRoute>
  );
}
