'use client';

import {
  MessageSquare,
  Search,
  BarChart3,
  Upload,
  Download,
  History,
  ShieldCheck,
  FileText,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth/auth-context-msal';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import AppShell from '@/components/brand/app-shell';
import InterlockingNc from '@/components/brand/interlocking-nc';
import { landingCopy } from '@/lib/landing/copy';

const FEATURE_ICONS = [
  MessageSquare,
  Search,
  BarChart3,
  Upload,
  Download,
  History,
  ShieldCheck,
  FileText,
];

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

      <section id="features" className="content-section" aria-labelledby="features-heading">
        <div className="site-wrap">
          <h2 id="features-heading" className="section-heading" tabIndex={-1}>
            {landingCopy.featuresHeading}
          </h2>
          <div className="feature-grid">
            {landingCopy.features.map((feature, index) => {
              const Icon = FEATURE_ICONS[index];
              return (
                <article key={feature.title} className="feature-card">
                  <span className="destination-icon">
                    <Icon strokeWidth={1.75} aria-hidden="true" />
                  </span>
                  <h3>{feature.title}</h3>
                  <p>{feature.description}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section id="about" className="navy-band" aria-labelledby="about-heading">
        <div className="about-band">
          <InterlockingNc className="about-watermark" />
          <div className="site-wrap about-inner">
            <h2 id="about-heading" className="about-heading" tabIndex={-1}>
              {landingCopy.aboutHeading}
            </h2>
            <div className="about-heading-rule" aria-hidden="true" />
            <ul className="about-facts">
              {landingCopy.aboutFacts.map((fact) => (
                <li key={fact.label}>
                  <p className="about-fact-label">{fact.label}</p>
                  <p className="about-fact-detail">{fact.detail}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
