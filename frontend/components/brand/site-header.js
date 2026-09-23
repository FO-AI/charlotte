'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { useAuth } from '@/lib/auth/auth-context-msal';
import UtilityBar from '@/components/brand/utility-bar';
import Logout from '@/components/logout';
import { Button } from '@/components/ui/button';

function navItemsFor({ isAuthenticated, isAccounting, isBanking, isAdmin, variant }) {
  if (variant === 'marketing' && !isAuthenticated) {
    return [
      { href: '#features', label: 'Features' },
      { href: '#about', label: 'About' },
    ];
  }

  const items = [];
  if (isAdmin) {
    items.push({ href: '/admin-landing', label: 'Admin' });
  }
  if (isAccounting || isAdmin) {
    items.push({ href: '/dashboard/accounting', label: 'Dashboard' });
    items.push({ href: '/chat', label: 'Chat' });
    items.push({ href: '/data-analysis', label: 'Data analysis' });
  }
  if (isBanking && !isAccounting) {
    items.push({ href: '/dashboard/banking', label: 'Dashboard' });
  }
  if (isBanking && isAdmin) {
    items.push({ href: '/dashboard/banking', label: 'Banking' });
  }
  return items;
}

function focusHashTarget(href) {
  if (!href.startsWith('#')) return;
  const headingId =
    href === '#features' ? 'features-heading' : href === '#about' ? 'about-heading' : href.slice(1);
  const el = document.getElementById(headingId) || document.getElementById(href.slice(1));
  if (el) {
    el.setAttribute('tabindex', '-1');
    el.focus();
  }
}

export default function SiteHeader({ variant = 'app' }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const toggleRef = useRef(null);
  const { login, loading, isAuthenticated, isAccounting, isBanking, isAdmin } = useAuth();
  const signedIn = isAuthenticated();
  const items = navItemsFor({
    isAuthenticated: signedIn,
    isAccounting,
    isBanking,
    isAdmin,
    variant,
  });

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <header>
      <UtilityBar />
      <div className="site-masthead">
        <div className="site-wrap site-masthead-inner">
          <Link href="/" className="site-identity">
            {variant === 'marketing' ? (
              <h1 className="site-title">Charlotte AI Platform</h1>
            ) : (
              <p className="site-title">Charlotte AI Platform</p>
            )}
            <span className="site-tagline">Finance and Operations</span>
          </Link>
          <div className="site-masthead-actions">
            {signedIn ? (
              <Logout />
            ) : (
              <Button
                id="sign-in"
                size="lg"
                onClick={() => login()}
                disabled={loading}
                className="site-signin min-h-[3.25rem] px-8 text-2xl font-bold bg-carolina text-white hover:bg-bolin hover:text-white"
              >
                {loading ? 'Signing in…' : 'Sign in'}
              </Button>
            )}
            {items.length > 0 && (
              <button
                ref={toggleRef}
                type="button"
                className="nav-toggle md:hidden"
                aria-expanded={open}
                aria-controls="primary-navigation"
                aria-label={open ? 'Close menu' : 'Open menu'}
                onClick={() => setOpen((prev) => !prev)}
              >
                {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
              </button>
            )}
          </div>
        </div>
      </div>
      {items.length > 0 && (
        <nav id="nav" className="site-nav" aria-label="Main">
          <div className="site-wrap">
            <ul
              id="primary-navigation"
              className={`site-nav-list ${open ? 'is-open' : ''}`}
            >
              {items.map((item) => {
                const current = item.href.startsWith('/') && pathname === item.href;
                const Comp = item.href.startsWith('#') ? 'a' : Link;
                return (
                  <li key={item.href}>
                    <Comp
                      href={item.href}
                      aria-current={current ? 'page' : undefined}
                      onClick={() => {
                        setOpen(false);
                        focusHashTarget(item.href);
                      }}
                    >
                      {item.label}
                    </Comp>
                  </li>
                );
              })}
            </ul>
          </div>
        </nav>
      )}
    </header>
  );
}
