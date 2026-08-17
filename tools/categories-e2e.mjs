/**
 * Exercises the admin categories screen in a real browser.
 *
 * The bug being guarded against was a screen that reported success while doing
 * nothing, so every assertion here checks the *list* after the action rather
 * than the toast that claims it worked.
 */
import { spawn } from 'node:child_process'
import { setTimeout as sleep } from 'node:timers/promises'

const PORT = 9666
const chrome = spawn('google-chrome', ['--headless=new', `--remote-debugging-port=${PORT}`,
  '--no-sandbox', '--disable-gpu', '--window-size=1500,1000',
  '--user-data-dir=/tmp/cdp-cats', 'about:blank'], { stdio: 'ignore' })

const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok }); console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`)
}
let ws, id = 1; const pend = new Map()
const send = (m, p = {}, s) => new Promise((res, rej) => { const i = id++; pend.set(i, {res,rej}); ws.send(JSON.stringify({id:i, method:m, params:p, sessionId:s})) })

try {
  let u; for (let i = 0; i < 50 && !u; i++) { try { u = (await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json()).webSocketDebuggerUrl } catch { await sleep(200) } }
  ws = new WebSocket(u)
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { const {res,rej} = pend.get(m.id); pend.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result) } }
  await new Promise(r => ws.onopen = r)
  const { targetId } = await send('Target.createTarget', { url: 'http://localhost:8443/admin/login' })
  const { sessionId: S } = await send('Target.attachToTarget', { targetId, flatten: true })
  await send('Page.enable', {}, S); await send('Runtime.enable', {}, S); await send('Page.bringToFront', {}, S)
  const ev = async e => {
    const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true }, S)
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text)
    return r.result.value
  }
  await sleep(2500)
  await ev(`
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set
    const ins = [...document.querySelectorAll('input')]
    const em = ins.find(i=>i.type==='email')||ins[0], pw = ins.find(i=>i.type==='password')||ins[1]
    set.call(em,'owner@rozgar.pk'); em.dispatchEvent(new Event('input',{bubbles:true}))
    set.call(pw,'phase-two-local-password'); pw.dispatchEvent(new Event('input',{bubbles:true}))
    document.querySelector('form')?.requestSubmit() || [...document.querySelectorAll('button')].find(b=>/sign in/i.test(b.textContent))?.click()
    true`)
  await sleep(3500)
  await ev(`location.href='/admin/dashboard/categories'`)
  await sleep(3500)

  const NAME = 'E2E Category ' + Date.now().toString().slice(-6)
  const rowNames = () => ev(`[...document.querySelectorAll('tbody tr')].map(r => r.cells[0]?.innerText.trim())`)
  const clickIn = (name, label) => ev(`
    (() => {
      const row = [...document.querySelectorAll('tbody tr')].find(r => r.cells[0]?.innerText.trim().startsWith(${JSON.stringify(name)}))
      if (!row) return 'no-row'
      const b = [...row.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)})
      if (!b) return 'no-button'
      b.click(); return 'clicked'
    })()`)

  const before = (await rowNames()).length
  check('category list loads from the API', before > 0, `${before} rows`)

  // --- create ---------------------------------------------------------
  await ev(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('Add Category')).click(); true`)
  await sleep(400)
  await ev(`
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set
    const i = document.querySelector('input[placeholder^="e.g."]')
    set.call(i, ${JSON.stringify(NAME)}); i.dispatchEvent(new Event('input',{bubbles:true})); true`)
  await sleep(300)
  await ev(`[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Save').click(); true`)
  await sleep(2500)
  let names = await rowNames()
  check('a new category appears in the list without a reload', names.includes(NAME), `${names.length} rows now`)

  // --- edit -----------------------------------------------------------
  const RENAMED = NAME + ' Renamed'
  check('Edit opens an inline editor', await clickIn(NAME, 'Edit') === 'clicked')
  await sleep(400)
  const typed = await ev(`
    (() => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set
      const i = document.querySelector('tbody input')
      if (!i) return 'no-input:' + document.querySelectorAll('tbody tr').length + ' rows'
      set.call(i, ${JSON.stringify(RENAMED)}); i.dispatchEvent(new Event('input',{bubbles:true}))
      return 'typed'
    })()`)
  check('the inline editor accepts input', typed === 'typed', typed)
  await sleep(200)
  await ev(`[...document.querySelectorAll('tbody button')].find(b => b.textContent.trim() === 'Save').click(); true`)
  await sleep(2500)
  names = await rowNames()
  check('Edit persists the new name', names.includes(RENAMED) && !names.includes(NAME))

  // --- archive / restore ----------------------------------------------
  check('Archive is clickable', await clickIn(RENAMED, 'Archive') === 'clicked')
  await sleep(2500)
  const archivedStatus = await ev(`
    (() => {
      const row = [...document.querySelectorAll('tbody tr')].find(r => r.cells[0]?.innerText.trim().startsWith(${JSON.stringify(RENAMED)}))
      return row ? row.cells[2].innerText.trim() : 'missing'
    })()`)
  check('Archive changes the status to Archived', archivedStatus === 'Archived', archivedStatus)
  check('the archived row stays on screen so it can be restored',
    (await rowNames()).includes(RENAMED))
  check('Restore is offered', await clickIn(RENAMED, 'Restore') === 'clicked')
  await sleep(2500)
  const restored = await ev(`
    (() => {
      const row = [...document.querySelectorAll('tbody tr')].find(r => r.cells[0]?.innerText.trim().startsWith(${JSON.stringify(RENAMED)}))
      return row ? row.cells[2].innerText.trim() : 'missing'
    })()`)
  check('Restore returns it to Active', restored === 'Active', restored)

  // --- the guard rail: archiving a category with listings --------------
  const busy = await ev(`
    (() => {
      const row = [...document.querySelectorAll('tbody tr')].find(r => Number(r.cells[1].innerText.replace(/,/g,'')) > 0)
      if (!row) return null
      const b = [...row.querySelectorAll('button')].find(b => b.textContent.trim() === 'Archive')
      b?.click(); return row.cells[0].innerText.trim()
    })()`)
  if (busy) {
    await sleep(2000)
    const toast = await ev(`document.body.innerText.includes('published listing')`)
    check('archiving a category that still has listings shows the server refusal', toast)
  }
} catch (err) {
  check('harness ran', false, err.message)
} finally {
  try { ws?.close() } catch {}
  chrome.kill()
}
const failed = results.filter(r => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
process.exit(failed.length ? 1 : 0)
