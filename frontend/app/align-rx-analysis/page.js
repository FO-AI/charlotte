'use client';

import ProtectedRoute from "@/components/protected-route";
import AlignRxAnalysis from "@/components/accounting/align-rx/align-rx-analysis";


export default function AlignRxAnalysisPage() {
  return (
    <ProtectedRoute>
      <AlignRxAnalysis />
    </ProtectedRoute>
  );
}