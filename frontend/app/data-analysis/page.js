'use client';

import ProtectedRoute from "@/components/protected-route";
import DataAnalysis from "@/components/accounting/data-analysis";
import AppShell from "@/components/brand/app-shell";

export default function DataAnalysisPage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <DataAnalysis />
      </AppShell>
    </ProtectedRoute>
  );
}
