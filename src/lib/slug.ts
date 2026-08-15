/**
 * URL-safe slug generation.
 *
 * Handles the en-dashes and parenthesised qualifiers that appear throughout the
 * job titles ("Software Engineer - Backend", "Product Designer (UX/UI)").
 */
export function slugify(input: string): string {
  return input
    .normalize('NFKD')
    // strip combining marks left behind by normalisation
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    // hyphen, en-dash, em-dash and friends collapse into plain separators
    .replace(/[‐-―]/g, '-')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Slug for a job listing, namespaced by company so titles can repeat. */
export function jobSlug(title: string, company: string): string {
  return `${slugify(title)}-at-${slugify(company)}`
}
