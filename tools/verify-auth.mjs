/**
 * Verifies the auth store's refresh behaviour without a browser.
 *
 * The project has no test runner, and this is the one piece of frontend logic
 * where a mistake is expensive rather than merely visible: the backend treats a
 * second rotation of an already-rotated refresh token as theft and revokes
 * every session in the family. Concurrent 401s must therefore produce exactly
 * one refresh call, not one per request.
 *
 * Vite's `ssrLoadModule` is used to load the TypeScript source with its `@`
 * aliases resolved, so this exercises the real module rather than a copy of it.
 *
 *     node tools/verify-auth.mjs
 */

import { createServer } from 'vite'

let failures = 0

function check(label, condition, detail = '') {
  const mark = condition ? '  ok  ' : ' FAIL '
  if (!condition) failures += 1
  console.log(`${mark} ${label}${detail ? ` — ${detail}` : ''}`)
}

/** Minimal localStorage so the storage helper's feature probe succeeds. */
function installBrowserGlobals() {
  const store = new Map()
  globalThis.window = globalThis
  globalThis.localStorage = {
    getItem: key => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
  }
}

async function main() {
  installBrowserGlobals()

  const server = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'error',
  })

  try {
    // --- a fetch stub that records what the client actually sends ----------
    const calls = []
    let refreshDelayMs = 20
    let refreshShouldFail = false

    globalThis.fetch = async (url, init = {}) => {
      const path = String(url)
      calls.push({ path, method: init.method ?? 'GET', headers: init.headers })

      if (path.includes('/auth/refresh')) {
        await new Promise(resolve => setTimeout(resolve, refreshDelayMs))
        if (refreshShouldFail) {
          return new Response(
            JSON.stringify({ type: 'x/errors/invalid_refresh_token', title: 'no', status: 401 }),
            { status: 401, headers: { 'content-type': 'application/json' } },
          )
        }
        return new Response(
          JSON.stringify({ access_token: 'fresh-token', expires_in: 900, expires_at: 'now' }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        )
      }

      if (path.includes('/auth/me')) {
        return new Response(
          JSON.stringify({ id: 'a1', email: 'a@b.pk', full_name: 'A', role: 'admin', permissions: ['JOB_EDIT'] }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        )
      }

      // Everything else answers 401 once, so the retry path is exercised.
      const authorization = new Headers(init.headers).get('Authorization')
      if (authorization === 'Bearer fresh-token') {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
      return new Response(JSON.stringify({ type: 'x/errors/invalid_token', title: 'no', status: 401 }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      })
    }

    const { useAuthStore } = await server.ssrLoadModule('/src/stores/useAuthStore.ts')
    const { api, ApiError } = await server.ssrLoadModule('/src/lib/http.ts')

    // --- 1. concurrent refreshes collapse into one request ----------------
    calls.length = 0
    const results = await Promise.all([
      useAuthStore.getState().refresh(),
      useAuthStore.getState().refresh(),
      useAuthStore.getState().refresh(),
      useAuthStore.getState().refresh(),
      useAuthStore.getState().refresh(),
    ])
    const refreshCalls = calls.filter(c => c.path.includes('/auth/refresh')).length
    check('five concurrent refreshes issue one network call', refreshCalls === 1, `${refreshCalls} call(s)`)
    check('every caller receives the same token', new Set(results).size === 1, results[0] ?? 'null')

    // --- 2. a later refresh is a new request, not a cached one ------------
    calls.length = 0
    await useAuthStore.getState().refresh()
    check(
      'a subsequent refresh is not memoised',
      calls.filter(c => c.path.includes('/auth/refresh')).length === 1,
    )

    // --- 3. concurrent 401s trigger one rotation, then all retry ----------
    useAuthStore.setState({ accessToken: 'stale-token', status: 'authenticated' })
    calls.length = 0
    refreshDelayMs = 30
    const responses = await Promise.all([
      api.get('/jobs'),
      api.get('/categories'),
      api.get('/locations'),
    ])
    const rotations = calls.filter(c => c.path.includes('/auth/refresh')).length
    check('three parallel 401s cause one rotation', rotations === 1, `${rotations} rotation(s)`)
    check('all three requests then succeed', responses.every(r => r.ok === true))

    // --- 4. a failed refresh gives up rather than looping ------------------
    useAuthStore.setState({ accessToken: 'stale-token', status: 'authenticated' })
    refreshShouldFail = true
    calls.length = 0
    let raised = null
    try {
      await api.get('/jobs')
    } catch (error) {
      raised = error
    }
    check('a dead session surfaces as an error', raised instanceof ApiError, raised?.name ?? 'none')
    check(
      'it does not retry the refresh in a loop',
      calls.filter(c => c.path.includes('/auth/refresh')).length === 1,
    )
    check('the store drops to anonymous', useAuthStore.getState().status === 'anonymous')
    check('the token is cleared', useAuthStore.getState().accessToken === null)

    // --- 5. auth calls never carry a bearer token -------------------------
    const refreshCall = calls.find(c => c.path.includes('/auth/refresh'))
    check(
      'refresh is sent anonymously',
      !new Headers(refreshCall?.headers).has('Authorization'),
    )
  } finally {
    await server.close()
  }

  console.log(failures === 0 ? '\nall checks passed' : `\n${failures} check(s) failed`)
  process.exit(failures === 0 ? 0 : 1)
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
