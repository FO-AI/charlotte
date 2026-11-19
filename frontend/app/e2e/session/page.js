'use client';

import Logout from '@/components/logout';
import { TestAuthProvider } from '@/lib/auth/auth-context-msal';

/**
 * Playwright harness: authenticated header logout controls without MSAL.
 * Only available when NEXT_PUBLIC_ENABLE_E2E_HARNESS=1 under non-production (next dev).
 */
const E2E_HARNESS =
  process.env.NEXT_PUBLIC_ENABLE_E2E_HARNESS === '1' && process.env.NODE_ENV !== 'production';

export default function SessionE2EPage() {
  if (!E2E_HARNESS) {
    return (
      <main className="min-h-screen p-6">
        <p>E2E harness disabled.</p>
      </main>
    );
  }

  return (
    <TestAuthProvider
      value={{
        logout: async () => {
          window.__e2eLogoutCalls = (window.__e2eLogoutCalls || 0) + 1;
        },
      }}
    >
      <main className="min-h-screen p-6">
        <Logout />
      </main>
    </TestAuthProvider>
  );
}
