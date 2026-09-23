export default function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="site-footer">
      <div className="site-wrap site-footer-inner">
        <a href="/" className="site-footer-mark">
          <img
            src="/logos/Finance_and_Operations_Signature_CarolinaBlue_White_rgb_h.png"
            alt="UNC Finance and Operations"
            width="474"
            height="150"
          />
        </a>
        <div className="site-footer-copy">
          <p>
            <strong>Charlotte</strong> is an internal AI workspace for
            University of North Carolina at Chapel Hill Finance and Operations
            employees.
          </p>
          <p>
            <a href="https://www.unc.edu/about/accessibility/">Accessibility</a>
            {" · "}
            <a href="https://www.unc.edu/about/privacy-statement/">Privacy</a>
          </p>
          <p>© {year} University of North Carolina at Chapel Hill</p>
        </div>
      </div>
    </footer>
  );
}
