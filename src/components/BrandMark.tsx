/**
 * The Plenilo logo.
 *
 * One component rather than a chip repeated in the header, footer, admin
 * sidebar and admin sign-in, so the mark is swapped in a single place. It
 * loads `public/logo.svg` — the same master `tools/generate-favicons.mjs`
 * rasterises the tab and home-screen icons from — as an `<img>` rather than
 * inline SVG, so the browser caches it once across every route.
 */
export default function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <img
      src="/logo.svg"
      alt="Plenilo.com"
      width={size}
      height={size}
      style={{ width: size, height: size, display: 'block', flexShrink: 0 }}
    />
  )
}
