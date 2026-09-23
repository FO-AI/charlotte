'use client';

import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth/auth-context-msal';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import AppShell from '@/components/brand/app-shell';
import { landingCopy } from '@/lib/landing/copy';

export default function Home() {
  const { login, loading, error, isAuthenticated, isAccounting, isBanking, isAdmin } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated()) {
      if (isAccounting) {
        router.push('/dashboard/accounting');
      } else if (isBanking) {
        router.push('/dashboard/banking');
      } else if (isAdmin) {
        router.push('/admin-landing');
      }
    }
  }, [isAuthenticated, isAccounting, isBanking, isAdmin, router]);

  return (
    <AppShell variant="marketing">
      <section className="hero-band">
        <div className="hero-panel">
          <div className="site-wrap">
            <h2>{landingCopy.heroHeading}</h2>
            <p>{landingCopy.heroBody}</p>
            <div className="mt-8">
              <Button
                type="button"
                onClick={() => login()}
                disabled={loading}
                size="lg"
                className="bg-navy text-white hover:bg-bolin min-h-12 px-8"
              >
                {loading ? landingCopy.signingIn : landingCopy.signIn}
              </Button>
            </div>
            {error && (
              <p className="mt-4 font-bold" role="alert">
                {landingCopy.signInFailed}
              </p>
            )}
          </div>
        </div>
        <aside className="hero-aside">
          <div className="hero-aside-media" />
          <div className="hero-aside-copy">
            <img
              className="hero-aside-logo"
              src="/logos/Finance_and_Operations_Signature_CarolinaBlue_White_rgb_h.png"
              alt=""
              aria-hidden="true"
            />
            <p>{landingCopy.heroAside}</p>
          </div>
        </aside>
      </section>
    </AppShell>
  );
}
