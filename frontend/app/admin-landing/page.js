/* 

This page will be the landing page for the admin
The page will have a header with the title "Admin Dashboard"
The page will have two main sections with the following options:
    - Accounting - routes to the accounting dashboard
    - Banking - routes to the banking dashboard
*/
'use client';

import ProtectedRoute from "@/components/protected-route";
import AdminLanding from "@/components/admin-landing";
import Logout from "@/components/logout";
export default function AdminLandingPage() {
    return (
        <ProtectedRoute>
            <Logout />
            <AdminLanding />
        </ProtectedRoute>
    );
}