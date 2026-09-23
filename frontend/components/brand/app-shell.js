import SkipLinks from '@/components/brand/skip-links';
import SiteHeader from '@/components/brand/site-header';
import SiteFooter from '@/components/brand/site-footer';

export default function AppShell({
  children,
  variant = 'app',
  compact = false,
  composerId = 'composer',
}) {
  const skipTargets =
    variant === 'marketing'
      ? [
          { href: '#main-content', label: 'Skip to main content' },
          { href: '#sign-in', label: 'Skip to sign in' },
        ]
      : [
          { href: '#main-content', label: 'Skip to main content' },
          { href: `#${composerId}`, label: 'Skip to composer' },
        ];

  return (
    <div className={`app-shell ${compact ? 'app-shell-compact' : ''}`}>
      <SkipLinks targets={skipTargets} />
      <SiteHeader variant={variant} />
      <main id="main-content" className="app-main" tabIndex={-1}>
        {children}
      </main>
      {!compact && <SiteFooter />}
    </div>
  );
}
