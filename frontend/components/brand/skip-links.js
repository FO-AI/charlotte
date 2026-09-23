export default function SkipLinks({ targets }) {
  const items = targets ?? [
    { href: '#main-content', label: 'Skip to main content' },
    { href: '#sign-in', label: 'Skip to sign in' },
  ];

  return (
    <nav aria-label="Skip" className="skip-links">
      {items.map((item) => (
        <a key={item.href} href={item.href}>
          {item.label}
        </a>
      ))}
    </nav>
  );
}
