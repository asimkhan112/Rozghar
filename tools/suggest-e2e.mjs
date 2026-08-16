/**
 * Drives a real browser against the dev server to exercise the autocomplete.
 *
 * The dropdown only exists while someone is typing into a focused field, so
 * none of it — debounce, keyboard navigation, outside click — is reachable
 * from the static snapshot harness. This talks CDP to a headless Chrome and
 * types like a person does.
 *
 * Usage: node tools/suggest-e2e.mjs [url]
 */
import { spawn } from 'node:child_process'
import { setTimeout as sleep } from 'node:timers/promises'

const URL_UNDER_TEST = process.argv[2] ?? 'http://localhost:8443/'
const PORT = 9222 + (Number(process.env.CDP_OFFSET) || 0)

const chrome = spawn('google-chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, '--no-sandbox',
  '--disable-gpu', '--window-size=1400,900', '--user-data-dir=/tmp/cdp-suggest',
  'about:blank',
], { stdio: 'ignore' })

const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`)
}

let ws, nextId = 1
const pending = new Map()
const send = (method, params = {}, sessionId) =>
  new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params, sessionId }))
  })

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json()
      return list.webSocketDebuggerUrl
    } catch { await sleep(200) }
  }
  throw new Error('chrome did not expose a debugging endpoint')
}

const evaluate = async (session, expression) => {
  const r = await send('Runtime.evaluate', {
    expression, returnByValue: true, awaitPromise: true,
  }, session)
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' :: ' + expression)
  return r.result.value
}

async function typeText(session, text) {
  for (const ch of text) {
    await send('Input.insertText', { text: ch }, session)
    await sleep(35)
  }
}

const KEYS = {
  ArrowDown: { windowsVirtualKeyCode: 40, code: 'ArrowDown' },
  ArrowUp: { windowsVirtualKeyCode: 38, code: 'ArrowUp' },
  Enter: { windowsVirtualKeyCode: 13, code: 'Enter' },
  Escape: { windowsVirtualKeyCode: 27, code: 'Escape' },
}
async function pressKey(session, key) {
  const meta = KEYS[key]
  await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key, ...meta }, session)
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key, ...meta }, session)
  await sleep(120)
}

const OPTIONS = '[role="option"]'

try {
  const wsUrl = await connect()
  ws = new WebSocket(wsUrl)
  ws.onmessage = e => {
    const msg = JSON.parse(e.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
    }
  }
  await new Promise(r => (ws.onopen = r))

  const { targetId } = await send('Target.createTarget', { url: URL_UNDER_TEST })
  const { sessionId: S } = await send('Target.attachToTarget', { targetId, flatten: true })
  await send('Page.enable', {}, S)
  await send('Runtime.enable', {}, S)
  // Key events are delivered to the focused page only; a headless target is
  // not focused until it is brought forward.
  await send('Page.bringToFront', {}, S)
  await sleep(2500)

  // --- focus the hero search field ------------------------------------
  await evaluate(S, `document.querySelector('input[role="combobox"]').focus()`)

  // --- 1. minimum length ----------------------------------------------
  await typeText(S, 'e')
  await sleep(600)
  check('single character opens nothing', await evaluate(S, `document.querySelectorAll('${OPTIONS}').length`) === 0)

  // --- 2. debounce: no request until typing settles --------------------
  // The API layer is axios, which uses XMLHttpRequest — a fetch spy would
  // count zero and pass regardless of how many requests actually went out.
  await evaluate(S, `
    window.__reqs = 0
    const open = window.XMLHttpRequest.prototype.open
    window.XMLHttpRequest.prototype.open = function (m, url, ...rest) {
      if (String(url).includes('/search/suggest')) window.__reqs++
      return open.call(this, m, url, ...rest)
    }
    true`)
  await typeText(S, 'ngineer')          // 7 more chars, fast
  const during = await evaluate(S, 'window.__reqs')
  await sleep(900)
  const after = await evaluate(S, 'window.__reqs')
  check('debounced: burst of 7 keystrokes issues few requests',
    after <= 3, `during burst=${during}, settled=${after}`)

  // --- 3. dropdown populated + grouped --------------------------------
  const count = await evaluate(S, `document.querySelectorAll('${OPTIONS}').length`)
  check('dropdown shows suggestions', count > 0, `${count} options`)
  const groups = await evaluate(S,
    `[...document.querySelectorAll('[role="group"]')].map(g => g.getAttribute('aria-label'))`)
  check('suggestions are grouped', Array.isArray(groups) && groups.length > 0, groups.join(', '))

  // --- 4. matched text highlighted ------------------------------------
  const marks = await evaluate(S,
    `[...document.querySelectorAll('${OPTIONS} mark')].map(m => m.textContent).filter(Boolean)`)
  check('typed text is highlighted', marks.length > 0 && marks.every(m => m.toLowerCase() === 'engineer'),
    JSON.stringify(marks.slice(0, 3)))

  // --- 5. keyboard navigation -----------------------------------------
  const selectedIndex = () => evaluate(S,
    `[...document.querySelectorAll('${OPTIONS}')].findIndex(o => o.getAttribute('aria-selected') === 'true')`)
  check('first row starts selected', await selectedIndex() === 0)
  await pressKey(S, 'ArrowDown')
  check('ArrowDown moves down', await selectedIndex() === 1, `index=${await selectedIndex()}`)
  await pressKey(S, 'ArrowDown')
  await pressKey(S, 'ArrowUp')
  check('ArrowUp moves back', await selectedIndex() === 1, `index=${await selectedIndex()}`)
  await pressKey(S, 'ArrowUp')
  await pressKey(S, 'ArrowUp')
  check('ArrowUp past the top wraps to the end',
    await selectedIndex() === count - 1, `index=${await selectedIndex()} of ${count}`)

  // --- 6. Escape closes ------------------------------------------------
  await pressKey(S, 'Escape')
  check('Escape closes the dropdown',
    await evaluate(S, `document.querySelectorAll('${OPTIONS}').length`) === 0)

  // --- 7. outside click closes ----------------------------------------
  await evaluate(S, `document.querySelector('input[role="combobox"]').focus()`)
  await typeText(S, ' ')
  await sleep(700)
  const reopened = await evaluate(S, `document.querySelectorAll('${OPTIONS}').length`)
  await evaluate(S, `
    document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
    true`)
  await sleep(200)
  check('outside click closes the dropdown',
    reopened > 0 && await evaluate(S, `document.querySelectorAll('${OPTIONS}').length`) === 0,
    `was ${reopened} options`)

  // --- 8. Enter selects and navigates ----------------------------------
  await evaluate(S, `
    const i = document.querySelector('input[role="combobox"]')
    i.focus()
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
    setter.call(i, 'engineer')
    i.dispatchEvent(new Event('input', { bubbles: true }))
    true`)
  await sleep(900)
  await pressKey(S, 'Enter')
  await sleep(1200)
  const url = await evaluate(S, 'location.pathname + location.search')
  check('Enter on a highlighted row navigates', url !== '/', url)
} catch (err) {
  check('harness ran', false, err.message)
} finally {
  try { ws?.close() } catch {}
  chrome.kill()
}

const failed = results.filter(r => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
process.exit(failed.length ? 1 : 0)
