'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context-msal';

export default function AuthCallback() {
  const [timedOut, setTimedOut] = useState(false);
  const router = useRouter();
  const { isAuthenticated, loading, department, isAccounting, isBanking, isAdmin, error } = useAuth();

  useEffect(() => {
    if (loading) return;

    if (!isAuthenticated()) {
      const timer = setTimeout(() => setTimedOut(true), 8000);
      return () => clearTimeout(timer);
    }

    // Wait briefly for department so we can land on the right dashboard
    if (isAccounting) {
      router.replace('/dashboard/accounting');
    } else if (isBanking) {
      router.replace('/dashboard/banking');
    } else if (isAdmin) {
      router.replace('/admin-landing');
    } else if (department === null) {
      // Still fetching department — stay on spinner
      return;
    } else {
      // Authenticated but no mapped department
      router.replace('/access-restricted');
    }
  }, [isAuthenticated, loading, department, isAccounting, isBanking, isAdmin, router]);

  if (error || timedOut) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 bg-destructive/10 rounded-full flex items-center justify-center mx-auto">
            <svg className="w-8 h-8 text-destructive" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-destructive">Authentication Failed</h1>
          <p className="text-muted-foreground max-w-md">
            {error || 'Sign-in did not complete. Popups are not required — try again, or allow redirects to login.microsoftonline.com.'}
          </p>
          <button
            onClick={() => window.location.href = '/'}
            className="bg-primary text-primary-foreground px-6 py-3 rounded-lg hover:bg-primary/90 transition-colors"
          >
            Return to Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-4">
        <div className="w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto"></div>
        <h1 className="text-2xl font-bold">Completing Authentication</h1>
        <p className="text-muted-foreground">Please wait while we sign you in...</p>
      </div>
    </div>
  );
}
