'use client';

import ChatLayout from "@/components/accounting/chat/chat-layout";
import ProtectedRoute from "@/components/protected-route";

export default function ChatPage() {
  return (
    <ProtectedRoute>
      <ChatLayout />
    </ProtectedRoute>
  );
}