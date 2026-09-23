'use client';

import ChatLayout from "@/components/accounting/chat/chat-layout";
import ProtectedRoute from "@/components/protected-route";
import AppShell from "@/components/brand/app-shell";

export default function ChatPage() {
  return (
    <ProtectedRoute>
      <AppShell compact>
        <ChatLayout />
      </AppShell>
    </ProtectedRoute>
  );
}
