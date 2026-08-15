// The status line that names the engineer and moves the visitor.
//
// A visitor arrives from a resume or an application and must learn whose work
// this is before they learn what it does. The bar reads as the machine's own
// header so the identity joins the world instead of sitting on top of it.

import { PROFILE } from "../profile";

const SECTIONS = [
  { href: "#architecture", label: "Architecture" },
  { href: "#approach", label: "Approach" },
  { href: "#contract", label: "Contract" },
  { href: "#demo", label: "Demo" },
];

export function SiteHeader() {
  return (
    <header className="site-header">
      <a className="header-identity" href="#top">
        <span className="header-name">{PROFILE.name}</span>
        <span className="header-role">{PROFILE.role}</span>
      </a>

      <nav className="header-nav" aria-label="Sections">
        {SECTIONS.map((section) => (
          <a key={section.href} href={section.href}>
            {section.label}
          </a>
        ))}
        <a
          className="header-source"
          href={PROFILE.repository}
          target="_blank"
          rel="noreferrer"
        >
          Source
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M8 16 16 8m0 0H9m7 0v7" />
          </svg>
        </a>
      </nav>
    </header>
  );
}
