/* 

This page will be the landing page for the admin
The page will have a header with the title "Admin Dashboard"
The page will have two main sections with the following options:
    - Accounting - routes to the accounting dashboard
    - Banking - routes to the banking dashboard
*/
'use client';

import { useRouter } from 'next/navigation';
import ProtectedRoute from "@/components/protected-route";
import { Button } from "@/components/ui/button";

function AdminLanding() {
    const router = useRouter();

    return (
        <div className="flex flex-col items-center py-12 gap-8">
            <h1 className="text-3xl font-bold mb-8">Admin Dashboard</h1>
            <div className="flex flex-row gap-8">
                <Button
                    className="bg-primary text-primary-foreground px-8 py-4 rounded-lg text-lg font-semibold hover:bg-primary/80 transition-colors"
                    onClick={() => router.push('/dashboard/accounting')}
                >
                    Accounting
                </Button>
                <Button
                    className="bg-primary text-primary-foreground px-8 py-4 rounded-lg text-lg font-semibold hover:bg-primary/80 transition-colors"
                    onClick={() => router.push('/dashboard/banking')}
                >
                    Banking
                </Button>
            </div>
        </div>
    );
}


export default function AdminLandingPage() {
    return (
        <ProtectedRoute>
            <AdminLanding />
        </ProtectedRoute>
    );
}