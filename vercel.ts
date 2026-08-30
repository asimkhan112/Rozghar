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
      '(Settings → Environment Variables), e.g. https://plenilo-api.up.railway.app',
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
  // `mv dist/index.html dist/app.html` is the same manoeuvre as the deletion
  // above, for the same reason and with worse consequences if it is skipped.
  //
  // Vercel resolves the filesystem before rewrites, and `/` resolves to
  // `index.html`. So the catch-all below — which gives every other URL on the
  // site its title, canonical, Open Graph tags, JSON-LD and server-rendered
  // body — was silently skipped for the home page, which served the built
  // shell byte-for-byte: the one page guaranteed to be read first was the only
  // page with no metadata and no content.
  //
  // Renaming the shell leaves nothing at `/` for the filesystem to match, so
  // the rewrite applies there like everywhere else. `api/prerender.ts` looks
  // for `app.html` first and still accepts `index.html`, so a build that has
  // not run this command degrades to today's behaviour rather than to a blank
  // site.
  buildCommand: 'pnpm build && rm -f dist/robots.txt && mv dist/index.html dist/app.html',
  outputDirectory: 'dist',
  framework: 'vite',

  rewrites: [
    // The API. Scoped to `/api/v1` rather than all of `/api` because
    // `api/prerender.ts` is itself served from this deployment at
    // `/api/prerender`, and a rule covering the whole prefix would leave the
    // two competing — resolvable only by the filesystem-precedence rule above,
    // which is far too subtle a thing for the site's entire HTML delivery to
    // rest on. `/api/v1` is the backend's complete browser-facing surface
    // (`settings.api_v1_prefix`, and `API_BASE` in `src/lib/http.ts`), so
    // narrowing costs nothing and makes the two disjoint by construction.
    routes.rewrite('/api/v1/(.*)', `${API_ORIGIN}/api/v1/$1`),

    // The two crawler endpoints, which the backend serves so their content can
    // reflect the live catalogue and the deployment environment.
    routes.rewrite('/sitemap.xml', `${API_ORIGIN}/sitemap.xml`),
    routes.rewrite('/robots.txt', `${API_ORIGIN}/robots.txt`),

    // Every page request. This replaces what used to be a plain rewrite to
    // `/index.html`: the shell is one file with one title and an empty
    // `<div id="root">`, so serving it directly meant every URL on the site
    // returned a document describing the homepage and containing no listing.
    // `api/prerender.ts` fetches that same shell and writes the page's real
    // title, description, Open Graph tags and JSON-LD into its head first.
    //
    // The path travels as a query parameter because a rewrite does not
    // reliably preserve the requested path in the function's own `req.url`.
    // The original query string is not forwarded and does not need to be: the
    // canonical URL drops it by policy (`siteMeta.ts`), and the browser's
    // address bar is untouched, so React Router still reads the filters from
    // `window.location` exactly as before.
    //
    // Static assets never reach here — the filesystem is resolved first, which
    // is what keeps `/assets/*`, the icons, and the `/index.html` the function
    // itself fetches out of this rule.
    routes.rewrite('/(.*)', '/api/prerender?path=/$1'),
  ],
}
