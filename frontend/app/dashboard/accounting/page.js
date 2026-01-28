/*
This is the dashboard page for the application
The dashboard page will be the main page for the application
It will have an aesthetic design 
the page should have some recent data numbers like total amount for current year so far (have a placeholder for now, will be wired up later)
there will be 4 main buttons:
    - Chat
    - Data analysis
    - EDI Viewer for CHS department
    - EDI viewer
*/

'use client';

import ProtectedRoute from "@/components/protected-route";
import Dashboard from "@/components/accounting/dashboard";
import AccessRestrictedPage from "@/app/access-restricted/page";
import { useAuth } from "@/lib/auth/auth-context-msal";
{/* TODO: Make the dashboard page more dynamic and interactive */}
import Logout from "@/components/logout";
export default function DashboardPage() {
  const { isAccounting, isAdmin } = useAuth();
  if (!isAccounting && !isAdmin) {
    return <AccessRestrictedPage />;
  }
  return (
    <ProtectedRoute>
      <Logout />
      <Dashboard />
    </ProtectedRoute>
  );
}