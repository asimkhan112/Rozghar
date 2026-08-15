/**
 * Compares two snapshot directories produced by render-snapshot.mjs.
 *
 * Style attributes are canonicalised before comparison — declarations are
 * trimmed and sorted — so reordering properties during a refactor is allowed
 * while any change to a value is reported. Everything else (markup structure,
 * text content, classes) is compared verbatim.
 *
 * Usage: node compare-snapshots.mjs <baselineDir> <candidateDir>
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const [baseDir, candDir] = process.argv.slice(2)
if (!baseDir || !candDir) throw new Error('usage: node compare-snapshots.mjs <baselineDir> <candidateDir>')

/** Sorts the declarations inside every style attribute. */
function canonicalise(html) {
  return html.replace(/style="([^"]*)"/g, (_, decls) => {
    const sorted = decls
      .split(';')
      .map(d => d.trim())
      .filter(Boolean)
      .sort()
      .join(';')
    return `style="${sorted}"`
  })
}

const baseFiles = readdirSync(baseDir).filter(f => f.endsWith('.html')).sort()
const candFiles = readdirSync(candDir).filter(f => f.endsWith('.html')).sort()

const problems = []
const missing = baseFiles.filter(f => !candFiles.includes(f))
const added = candFiles.filter(f => !baseFiles.includes(f))
if (missing.length) problems.push(`missing snapshots: ${missing.join(', ')}`)
if (added.length) problems.push(`unexpected snapshots: ${added.join(', ')}`)

let identical = 0
for (const file of baseFiles) {
  if (!candFiles.includes(file)) continue
  const a = canonicalise(readFileSync(join(baseDir, file), 'utf8'))
  const b = canonicalise(readFileSync(join(candDir, file), 'utf8'))
  if (a === b) {
    identical++
    continue
  }
  // Report the first divergence with surrounding context.
  let i = 0
  while (i < a.length && i < b.length && a[i] === b[i]) i++
  const from = Math.max(0, i - 90)
  problems.push(
    `${file}: diverges at offset ${i}\n` +
    `  baseline:  …${a.slice(from, i + 90)}\n` +
    `  candidate: …${b.slice(from, i + 90)}`,
  )
}

console.log(`${identical}/${baseFiles.length} snapshots identical`)
if (problems.length) {
  console.log('\nDIFFERENCES FOUND:\n')
  console.log(problems.join('\n\n'))
  process.exit(1)
}
console.log('PASS: rendered output is visually identical')
