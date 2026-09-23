"use client";

import EDIReportsViewer from "@/components/accounting/edi-reports-viewer";
import ProtectedRoute from "@/components/protected-route";
import AppShell from "@/components/brand/app-shell";

export default function EDIViewerPage() {
  return (
    <ProtectedRoute>
      <AppShell>
        <EDIReportsViewer />
      </AppShell>
    </ProtectedRoute>
  );
}
