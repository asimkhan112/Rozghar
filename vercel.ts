import { routes, type VercelConfig } from '@vercel/config/v1'

/**
 * Vercel deployment configuration.
 *
 * `vercel.ts` rather than `vercel.json` because the backend's address is an
 * environment value, and only the TypeScript form is evaluated at build time
 * where `process.env` exists. That keeps the deployed host out of the
 * repository: moving the API elsewhere is a dashboard change.
 *
 * ## Why the API is proxied rather than called directly
 *
 * `src/lib/http.ts` sets `API_BASE = "/api/v1"` — a *relative* URL — so the
 * browser only ever talks to the origin it loaded from. These rewrites keep
 * that true in production: the deployed app has the same single-origin shape
 * as local development, where Vite proxies the identical three paths.
 *
 * That is not tidiness. The admin refresh cookie is `SameSite=Strict`. If the
 * browser called the backend's own hostname, that cookie would be cross-site
 * and would not be sent — admin sign-in would break, and the fix would be to
 * weaken the cookie to `SameSite=None` and add CORS to the API. Proxying
 * avoids both changes, so nothing about the application has to know it is
 * deployed on Vercel.
 */

const API_ORIGIN = process.env.API_ORIGIN?.replace(/\/$/, '')

if (!API_ORIGIN) {
  // Failing the build is the point. Without this the rewrites silently vanish
  // and every API call returns the SPA's index.html with a 200, which looks
  // like a JSON parsing bug rather than a missing setting.
  throw new Error(
    'API_ORIGIN is not set. Add it to the Vercel project environment ' +
      '(Settings → Environment Variables), e.g. https://rozgar-api.up.railway.app',
  )
}

export const config: VercelConfig = {
  // The build emits a static `dist/robots.txt` (generated from
  // `.figma/make/site.json`), and Vercel gives "precedence to the filesystem
  // prior to rewrites being applied" — so that file would shadow the rewrite
  // below and pin the deployment to whatever `site.json` last said. Removing
  // it lets the backend answer, which is what makes the response
  // environment-aware: `Disallow: /` on staging, the real policy in
  // production, decided by the API rather than by a build artefact.
  buildCommand: 'pnpm build && rm -f dist/robots.txt',
  outputDirectory: 'dist',
  framework: 'vite',

  rewrites: [
    // The API and the two crawler endpoints, which the backend serves.
    routes.rewrite('/api/(.*)', `${API_ORIGIN}/api/$1`),
    routes.rewrite('/sitemap.xml', `${API_ORIGIN}/sitemap.xml`),
    routes.rewrite('/robots.txt', `${API_ORIGIN}/robots.txt`),

    // Single-page-app fallback, last so it cannot shadow the rules above.
    // Without it, reloading /jobs/some-slug returns a Vercel 404: only
    // index.html exists on disk, and React Router never sees the path.
    routes.rewrite('/(.*)', '/index.html'),
  ],
}
