import { createServer } from 'vite'
const server = await createServer({
  root: process.cwd(), configFile: 'vite.config.ts',
  server: { middlewareMode: true }, appType: 'custom', logLevel: 'error',
})
const { diffWords, draftToFields } = await server.ssrLoadModule('/src/components/AIDraftReview.tsx')

const cases = [
  ['typo fix', 'we are lookng for a senior enginer', 'We are looking for a senior engineer'],
  ['identical', 'same text exactly', 'same text exactly'],
  ['from empty', '', 'brand new content appears here'],
  ['to empty', 'content that gets deleted entirely', ''],
  ['middle edits', 'a b c d e f g', 'a x c d y f g'],
  ['reorder', 'alpha beta gamma', 'gamma beta alpha'],
]

let failures = 0
for (const [name, before, after] of cases) {
  const [l, r] = diffWords(before, after)
  const lText = l.map(p => p.text).join('')
  const rText = r.map(p => p.text).join('')
  // Reassembly must reproduce the source exactly (trailing space aside).
  const ok = lText.trimEnd() === before.trimEnd() && rText.trimEnd() === after.trimEnd()
  const marked = [l.filter(p => p.changed).length, r.filter(p => p.changed).length]
  if (!ok) failures++
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name.padEnd(13)} removed=${marked[0]} added=${marked[1]}`)
}
const identical = diffWords('same text exactly', 'same text exactly')
console.log('identical text marks nothing:', identical.every(side => side.every(p => !p.changed)))
console.log('\nfailures:', failures)
await server.close()
process.exit(failures ? 1 : 0)
