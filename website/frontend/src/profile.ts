// The one place the site states who built the platform.
//
// The page is a job-application artifact, so the identity is content, not
// decoration. Every link is optional: an empty string removes its control from
// the header and the footer, so an unset value never ships as a dead link.
//
// FILL THESE IN before the site becomes public: `linkedin` and `resume` are
// empty, and `email` carries a personal address that a dedicated one SHOULD
// replace.

export interface ProfileLink {
  label: string;
  href: string;
}

export const PROFILE = {
  name: "Emanuel Cortes Lugo",
  /** Read beside the name. It names the work, not a seniority claim. */
  role: "Platform & MLOps Engineer",
  /** One line under the name in the footer. Keep it to a single sentence. */
  summary:
    "I build the infrastructure that carries machine learning models — " +
    "pipelines, deployment boundaries, and the monitoring that closes the loop.",
  email: "pepi91cl@gmail.com",
  linkedin: "",
  resume: "",
  github: "https://github.com/emanuelGitCodes",
  repository: "https://github.com/emanuelGitCodes/aws-mlops-platform",
} as const;

/** Build the contact links that hold a value, in the order the footer shows. */
export function contactLinks(): ProfileLink[] {
  return CANDIDATES.filter((link) => link.href !== "");
}

/**
 * Name the contacts that are still empty.
 *
 * The footer shows these during development only, so an unset value is
 * visible while the site is being built and can never reach a visitor. An
 * empty link that simply disappears is how a site ships without its own
 * contact details.
 */
export function missingLinks(): string[] {
  if (!import.meta.env.DEV) return [];
  return CANDIDATES.filter((link) => link.href === "").map((link) => link.label);
}

const CANDIDATES: ProfileLink[] = [
  { label: "Email", href: PROFILE.email ? `mailto:${PROFILE.email}` : "" },
  { label: "LinkedIn", href: PROFILE.linkedin },
  { label: "Resume", href: PROFILE.resume },
  { label: "GitHub", href: PROFILE.github },
];

/**
 * Read the visible text for a link.
 *
 * The value column shows the destination, never the label again. A mailto
 * shows the address, and a URL shows its host and path without the scheme.
 */
export function linkText(link: ProfileLink): string {
  if (link.href.startsWith("mailto:")) return link.href.slice("mailto:".length);
  return link.href.replace(/^https?:\/\//, "").replace(/\/$/, "");
}
