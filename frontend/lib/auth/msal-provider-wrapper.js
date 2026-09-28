'use client';

import { useEffect, useState } from 'react';
import { MsalProvider } from "@azure/msal-react";
import { msalInstance } from './auth-config';
import { AuthProvider, TestAuthProvider } from './auth-context-msal';

const E2E_HARNESS = process.env.NEXT_PUBLIC_ENABLE_E2E_HARNESS === '1';

export default function MsalProviderWrapper({ children }) {
  const [ready, setReady] = useState(E2E_HARNESS);

  useEffect(() => {
    if (E2E_HARNESS) return undefined;

    let cancelled = false;

    (async () => {
      try {
        await msalInstance.initialize();
        // Completes redirect login and restores the account into cache
        await msalInstance.handleRedirectPromise();
      } catch (error) {
        console.error('MSAL redirect handling failed:', error);
      } finally {
        if (!cancelled) setReady(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (E2E_HARNESS) {
    return <TestAuthProvider>{children}</TestAuthProvider>;
  }

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <MsalProvider instance={msalInstance}>
      <AuthProvider>
        {children}
      </AuthProvider>
    </MsalProvider>
  );
}
