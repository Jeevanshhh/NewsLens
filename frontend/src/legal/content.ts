/**
 * Static legal / informational content for NewsLens.
 *
 * These pages are intentionally plain-text and honest. They describe what the
 * prototype actually does and explicitly do NOT claim certification or full
 * statutory compliance - a real operator must complete its own legal review
 * before launch (the contact details below are placeholders to be replaced).
 */

export interface LegalSection {
  heading?: string;
  paragraphs: string[];
}

export interface LegalDoc {
  slug: string;
  title: string;
  updated: string;
  intro: string;
  sections: LegalSection[];
}

export const LAST_UPDATED = "2026-09-24";

// A single, clearly-marked contact placeholder. Replace before public launch.
export const CONTACT_EMAIL = "hello@example.newslens.local";

export const LEGAL_NAV: { slug: string; label: string }[] = [
  { slug: "about", label: "About" },
  { slug: "privacy", label: "Privacy" },
  { slug: "terms", label: "Terms" },
  { slug: "security", label: "Security" },
  { slug: "copyright", label: "Copyright" },
  { slug: "contact", label: "Contact" },
];

export const LEGAL_DOCS: Record<string, LegalDoc> = {
  about: {
    slug: "about",
    title: "About NewsLens",
    updated: LAST_UPDATED,
    intro:
      "NewsLens is a search-first news discovery and research tool. It helps you find, read, organise and analyse news coverage across many public sources from one place.",
    sections: [
      {
        heading: "What it does",
        paragraphs: [
          "You run a search and NewsLens collects matching headlines from configured news providers, de-duplicates them, and stores structured metadata (title, source, publication time, detected topic and location) so you can browse, filter and bookmark results.",
          "Analytics are computed only from the articles actually collected - counts and distributions are derived from real stored data, never invented.",
        ],
      },
      {
        heading: "How articles are labelled",
        paragraphs: [
          "Each article is first classified by a fast, transparent rules layer (publisher domain and headline keywords). When a rules-based topic is uncertain, an optional small machine-learning model (TF-IDF + Complement Naive Bayes) suggests a general news topic.",
          "The classifier is a research baseline, not a polished product: it can be wrong and abstains when unsure. Topic labels are best-effort aids for browsing, not authoritative categorisation.",
        ],
      },
      {
        heading: "What it is not",
        paragraphs: [
          "NewsLens does not write articles, endorse sources, or guarantee accuracy. It is an aggregation and analysis aid. Full editorial content and copyright belong to the original publishers.",
        ],
      },
    ],
  },

  privacy: {
    slug: "privacy",
    title: "Privacy Policy",
    updated: LAST_UPDATED,
    intro:
      "This page explains what personal data NewsLens handles and what you can do about it. It is provided in good faith for a research prototype and is not a representation that NewsLens has completed any formal compliance certification.",
    sections: [
      {
        heading: "Data we store about you",
        paragraphs: [
          "Account data: your name and email address, and a password hash (we never store your password in plain text).",
          "Activity data tied to your account: your searches, saved searches, bookmarks and generated report records. Searches you run while signed out are stored only against the anonymous scope.",
          "The shared article corpus itself is global research data and is not attributed to you.",
        ],
      },
      {
        heading: "How we use it",
        paragraphs: [
          "To provide the features you asked for: personalised search history, bookmarks, saved searches, and analytics scoped to your own activity.",
          "We do not sell personal data. This prototype does not embed third-party advertising or tracking scripts.",
        ],
      },
      {
        heading: "Authentication and storage",
        paragraphs: [
          "Sessions use short-lived signed access tokens (JWT). Your token is kept in your browser's local storage and sent as an authorization header.",
          "Changing or resetting your password invalidates tokens issued beforehand, so older sessions stop working.",
        ],
      },
      {
        heading: "Your controls",
        paragraphs: [
          "You can export all personal data NewsLens holds about you (Settings → Your data) as a JSON file at any time.",
          "You can permanently delete your account and its associated personal data (Settings → Delete account). Deletion erases your searches, bookmarks and report records.",
        ],
      },
      {
        heading: "Note on India's DPDP Act",
        paragraphs: [
          "NewsLens is designed around capabilities that align with the rights contemplated by India's Digital Personal Data Protection Act, 2023 - notably access/portability (data export), erasure (account deletion), and a security posture described on the Security page.",
          "However, this is a research prototype. It does NOT claim to be a complete or certified DPDP implementation. A production operator must run its own data-protection impact assessment, publish a real grievance contact, define lawful bases and retention, and implement consent management appropriate to their deployment.",
        ],
      },
    ],
  },

  terms: {
    slug: "terms",
    title: "Terms of Use",
    updated: LAST_UPDATED,
    intro:
      "By using NewsLens you agree to these terms. They are written for a research/prototype service and may change.",
    sections: [
      {
        heading: "Acceptable use",
        paragraphs: [
          "Use NewsLens to read and research public news coverage. Do not abuse the service: no attempts to break authentication, overwhelm the API, scrape at abusive rates, or upload malicious content.",
          "Login attempts are rate-limited to protect accounts. Accounts used for abuse may be suspended or deleted.",
        ],
      },
      {
        heading: "Content and sources",
        paragraphs: [
          "NewsLens shows headlines, short descriptions and links gathered from third-party news providers and publishers. It does not claim ownership of that content and does not necessarily reflect the views of any source.",
        ],
      },
      {
        heading: "No warranty",
        paragraphs: [
          "The service is provided “as is”, without warranty of any kind. Classification, analytics and search results may be incomplete or incorrect. Do not rely on NewsLens as your sole source for any decision.",
        ],
      },
      {
        heading: "Your account",
        paragraphs: [
          "Keep your credentials safe. You are responsible for activity under your account. You can close your account at any time via Settings.",
        ],
      },
    ],
  },

  security: {
    slug: "security",
    title: "Security",
    updated: LAST_UPDATED,
    intro:
      "NewsLens takes reasonable, proportionate measures to protect the service and your data, and describes them openly here.",
    sections: [
      {
        heading: "Measures in place",
        paragraphs: [
          "Passwords are hashed with a memory-hard key-derivation function (scrypt) using per-password salts; plain passwords are never stored or logged.",
          "Access tokens are signed (HS256 JWT) and expire. Changing or resetting a password revokes previously issued tokens.",
          "The login endpoint is rate-limited to slow brute-force attempts.",
          "API responses carry hardening headers (content-type sniffing disabled, framing denied, a restrictive content-security policy, referrer limits).",
          "Errors returned to clients are generic; technical detail is logged server-side only, and secrets are never included in logs or health output.",
          "Production boot fails closed on insecure configuration (a default signing key or credentialed wildcard CORS).",
        ],
      },
      {
        heading: "Reporting a vulnerability",
        paragraphs: [
          `If you believe you have found a security issue, please contact us privately at ${CONTACT_EMAIL} rather than disclosing it publicly.`,
          "This is a research prototype and does not currently operate a paid bug-bounty programme. We ask for reasonable time to investigate before any public disclosure.",
        ],
      },
    ],
  },

  copyright: {
    slug: "copyright",
    title: "Copyright",
    updated: LAST_UPDATED,
    intro:
      "NewsLens aggregates references to news content; it does not claim copyright over publishers' work.",
    sections: [
      {
        heading: "Ownership",
        paragraphs: [
          "All article titles, descriptions, images and full text remain the property of their respective publishers. NewsLens displays limited metadata and links to the original sources to support discovery and research.",
        ],
      },
      {
        heading: "Takedown requests",
        paragraphs: [
          `If you are a rights holder and believe content should be removed or unlinked from NewsLens, contact ${CONTACT_EMAIL} with the specific URLs and your basis for the request, and we will review it.`,
          "Formal notices should still be sent to the original publisher, who controls the underlying material.",
        ],
      },
    ],
  },

  contact: {
    slug: "contact",
    title: "Contact",
    updated: LAST_UPDATED,
    intro: "There are a few ways to reach the team behind NewsLens.",
    sections: [
      {
        heading: "Email",
        paragraphs: [
          `General enquiries, privacy requests and security reports: ${CONTACT_EMAIL}`,
          "This address is a placeholder. Before a public launch the operator of this deployment should publish a monitored, real contact point here.",
        ],
      },
      {
        heading: "In-product",
        paragraphs: [
          "You can exercise your data rights without email at all: export your data or delete your account from the Settings page while signed in.",
        ],
      },
    ],
  },
};
