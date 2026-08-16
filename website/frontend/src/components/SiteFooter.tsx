// The close of the page: who built it, and how to reach him.
//
// The footer is the visitor's exit. A hiring reader who scrolled this far has
// decided the work is worth a message, so contact is the content here and the
// links carry the whole weight.

import { PROFILE, contactLinks, linkText, missingLinks } from "../profile";

export function SiteFooter() {
  const links = contactLinks();
  const missing = missingLinks();

  return (
    <footer className="site-footer" id="contact">
      <div className="footer-identity">
        <p className="footer-name">{PROFILE.name}</p>
        <p className="footer-role">{PROFILE.role}</p>
        <p className="footer-summary">{PROFILE.summary}</p>
      </div>

      <div className="footer-contact">
        <h2>Get in touch</h2>
        <ul>
          {links.map((link) => (
            <li key={link.label}>
              <a
                href={link.href}
                {...(link.href.startsWith("http")
                  ? { target: "_blank", rel: "noreferrer" }
                  : {})}
              >
                <span className="contact-label">{link.label}</span>
                <span className="contact-value">{linkText(link)}</span>
              </a>
            </li>
          ))}
          {missing.map((label) => (
            <li className="contact-missing" key={label}>
              <span className="contact-label">{label}</span>
              <span className="contact-value">
                not set — fill this in <code>src/profile.ts</code>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </footer>
  );
}
