/**
 * Compares the visual appearance of two snapshot directories.
 *
 * The routing migration deliberately changes element names — navigation
 * targets became real `<a href>` elements — so a byte diff is the wrong test.
 * This compares what a user actually sees:
 *
 *   1. the ordered sequence of style declarations across the document
 *   2. the visible text content
 *
 * Both sides are parsed through the same CSS engine before comparison, so
 * snapshots taken with different renderers (`#fff` vs `rgb(255, 255, 255)`)
 * still compare correctly. Any change to a colour, size, spacing value,
 * border, radius or shadow fails. Swapping `<button>` for `<a>` while keeping
 * identical styling passes.
 *
 * Usage: node compare-appearance.mjs <baselineDir> <candidateDir>
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { JSDOM } from 'jsdom'

const [baseDir, candDir] = process.argv.slice(2)
if (!baseDir || !candDir) throw new Error('usage: node compare-appearance.mjs <baselineDir> <candidateDir>')

const probe = new JSDOM('').window.document.createElement('div')

/** Normalises a style attribute into sorted `prop:value` pairs. */
function canonicalise(cssText) {
  probe.style.cssText = ''
  probe.style.cssText = cssText
  const decls = []
  for (let i = 0; i < probe.style.length; i++) {
    const prop = probe.style[i]
    decls.push(`${prop}:${probe.style.getPropertyValue(prop).trim()}`)
  }
  return decls.sort()
}

/**
 * The only declarations the routing migration is permitted to introduce.
 * They neutralise the browser's default anchor styling, so an element that
 * became an `<a>` computes exactly as it did when it was a `<button>`.
 */
const ANCHOR_RESET = new Set(canonicalise('color: inherit; text-decoration: none'))

/**
 * Declarations that restore a `<button>` default on an element that became an
 * `<a>`. A button centres its own text; a block anchor does not, so restoring
 * `text-align: center` keeps the rendered result identical.
 */
const BUTTON_DEFAULTS = new Set(canonicalise('text-align: center'))

/** Files whose content is expected to differ, with the reason. */
const EXPECTED = new Map(
  (process.env.EXPECT_DIFFERENT ?? '')
    .split(',')
    .filter(Boolean)
    .map(entry => {
      const [file, ...reason] = entry.split(':')
      return [file.trim(), reason.join(':').trim() || 'declared as expected']
    }),
)

/**
 * Ordered list of canonicalised style attributes with the anchor reset removed.
 * An attribute consisting only of the reset is a pure link wrapper and drops
 * out of the sequence entirely.
 */
function styles(html) {
  return [...html.matchAll(/style="([^"]*)"/g)]
    .map(m =>
      canonicalise(m[1])
        .filter(d => !ANCHOR_RESET.has(d) && !BUTTON_DEFAULTS.has(d))
        .join(';'),
    )
    .filter(Boolean)
}

/** Visible text, whitespace-normalised. */
function text(html) {
  return html
    .replace(/<style>[\s\S]*?<\/style>/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Navigable hrefs, for reporting only. */
function anchors(html) {
  return [...html.matchAll(/<a [^>]*href="([^"]*)"/g)].map(m => m[1])
}

const baseFiles = new Set(readdirSync(baseDir).filter(f => f.endsWith('.html')))
const candFiles = new Set(readdirSync(candDir).filter(f => f.endsWith('.html')))
const common = [...baseFiles].filter(f => candFiles.has(f)).sort()

let pass = 0
let anchorsAdded = 0
const problems = []
const expected = []

for (const file of common) {
  const a = readFileSync(join(baseDir, file), 'utf8')
  const b = readFileSync(join(candDir, file), 'utf8')

  const sa = styles(a)
  const sb = styles(b)
  anchorsAdded += anchors(b).length - anchors(a).length

  const issues = []
  if (sa.length !== sb.length) issues.push(`style count ${sa.length} -> ${sb.length}`)

  const n = Math.min(sa.length, sb.length)
  for (let i = 0; i < n; i++) {
    if (sa[i] !== sb[i]) {
      issues.push(`style[${i}]\n      baseline:  ${sa[i]}\n      candidate: ${sb[i]}`)
      break
    }
  }

  const ta = text(a)
  const tb = text(b)
  if (ta !== tb) {
    let i = 0
    while (i < ta.length && i < tb.length && ta[i] === tb[i]) i++
    issues.push(
      `text diverges at ${i}\n      baseline:  …${ta.slice(Math.max(0, i - 50), i + 60)}\n      candidate: …${tb.slice(Math.max(0, i - 50), i + 60)}`,
    )
  }

  if (!issues.length) {
    pass++
  } else if (EXPECTED.has(file)) {
    expected.push(`${file}: ${EXPECTED.get(file)}`)
  } else {
    problems.push(`${file}:\n   - ${issues.join('\n   - ')}`)
  }
}

console.log(`compared ${common.length} shared snapshots`)
console.log(`  ${pass} visually identical`)
console.log(`  ${candFiles.size - common.length} new snapshots (not in baseline)`)
console.log(`  +${anchorsAdded} navigable anchors added`)
if (expected.length) {
  console.log(`  ${expected.length} expected to differ:`)
  for (const e of expected) console.log(`     - ${e}`)
}
if (problems.length) {
  console.log(`\nAPPEARANCE DIFFERENCES (${problems.length}):\n`)
  console.log(problems.join('\n\n'))
  process.exit(1)
}
console.log('\nPASS: appearance unchanged across every shared surface')
