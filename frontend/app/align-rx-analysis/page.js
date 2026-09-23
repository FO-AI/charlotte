'use client';

import ProtectedRoute from "@/components/protected-route";
import AlignRxAnalysis from "@/components/accounting/align-rx/align-rx-analysis";
import AppShell from "@/components/brand/app-shell";

export default function AlignRxAnalysisPage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <AlignRxAnalysis />
      </AppShell>
    </ProtectedRoute>
  );
}
