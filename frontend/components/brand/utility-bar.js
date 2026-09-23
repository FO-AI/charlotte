import InterlockingNc from "@/components/brand/interlocking-nc";

const LINKS = [
  { href: "https://www.unc.edu/about/accessibility/", label: "Accessibility" },
  { href: "https://www.unc.edu/events/", label: "Events", overflow: true },
  { href: "https://library.unc.edu/", label: "Libraries", overflow: true },
  { href: "https://maps.unc.edu/", label: "Maps" },
  { href: "https://www.unc.edu/a-z/", label: "Departments" },
  { href: "https://connectcarolina.unc.edu/", label: "ConnectCarolina", overflow: true },
  { href: "https://www.unc.edu/search", label: "UNC Search", id: "unc-search" },
];

export default function UtilityBar() {
  const overflowLinks = LINKS.filter((link) => link.overflow);

  return (
    <div id="unc-utility-bar" className="utility-bar" data-color="blue">
      <div className="utility-bar-container">
        <nav aria-label="skip">
          <a href="#unc-search" className="utility-bar-skip-link">
            Skip to the end of the global utility bar
          </a>
        </nav>
        <div className="utility-bar-row">
          <a
            href="https://www.unc.edu/"
            id="utility-bar-unc-link"
            className="utility-bar-home"
            aria-labelledby="unc-ub-title"
          >
            <InterlockingNc id="unc-interlocking-logo" />
            <span id="unc-ub-title">The University of North Carolina at Chapel Hill</span>
          </a>
          <ul id="utility-bar-nav" className="utility-bar-nav">
            {LINKS.map((link) => (
              <li key={link.href} className={link.overflow ? "max-lg:hidden" : undefined}>
                <a href={link.href} id={link.id} className="utility-bar-link">
                  {link.label}
                </a>
              </li>
            ))}
            <li className="utility-bar-more lg:hidden">
              <details>
                <summary>More campus links</summary>
                <ul className="utility-bar-more-list">
                  {overflowLinks.map((link) => (
                    <li key={link.href}>
                      <a href={link.href}>{link.label}</a>
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
