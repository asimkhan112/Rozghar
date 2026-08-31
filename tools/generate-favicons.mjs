/**
 * Renders the Plenilo mark into the raster icon formats a browser asks for.
 *
 * `public/logo.svg` is the master — the same file the site header loads — and
 * covers every current browser, but a tab icon is the one asset that still has
 * to answer to old rules: Safari before 17 and every Windows shell surface want
 * an .ico, iOS wants a non-transparent 180px PNG for the home screen, and
 * Android reads the sizes named in the web manifest. So the mark is described
 * once, in the master, and every other format is rasterised from it — which is
 * what keeps the tab, the home screen and the install prompt showing the same
 * logo.
 *
 * The tab and home-screen icons sit the mark on a rounded white card rather
 * than letting it float: its dark wedge would disappear against a dark tab
 * strip, and iOS refuses transparency on the home screen anyway.
 *
 * Run after editing `public/logo.svg`:  node tools/generate-favicons.mjs
 */

import { deflateSync } from 'node:zlib'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const OUT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../public')
const MASTER = path.join(OUT_DIR, 'logo.svg')

const CARD = [0xff, 0xff, 0xff]
const CANVAS = 64
const CORNER_RADIUS = 14
/** Share of the card the mark spans, so it is not crowded against the corners. */
const MARK_INSET = 0.78

/** Points along a circular arc, in degrees, clockwise in screen coordinates. */
function arc(cx, cy, r, from, to, steps = 32) {
  const points = []
  for (let i = 0; i <= steps; i++) {
    const angle = ((from + ((to - from) * i) / steps) * Math.PI) / 180
    points.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)])
  }
  return points
}

/** The background plate. Squared off for iOS, which applies its own mask. */
function plate(rounded) {
  if (!rounded) return [[[0, 0], [CANVAS, 0], [CANVAS, CANVAS], [0, CANVAS]]]
  const r = CORNER_RADIUS
  const e = CANVAS
  return [[
    ...arc(r, r, r, 180, 270),
    ...arc(e - r, r, r, 270, 360),
    ...arc(e - r, e - r, r, 0, 90),
    ...arc(r, e - r, r, 90, 180),
  ]]
}

/**
 * The master's paths are straight-line contours traced from the artwork, so
 * these read the two commands they use rather than pulling in an SVG library.
 */
function parseContours(d) {
  return d.split('Z').filter(sub => sub.trim()).map(sub =>
    sub.replace(/^M/, '').split('L').map(pair => pair.trim().split(/[\s,]+/).map(Number))
  )
}

/** Each fill in the master, scaled down into the card and centred. */
function readMaster() {
  const svg = readFileSync(MASTER, 'utf8')
  const offset = (CANVAS * (1 - MARK_INSET)) / 2
  const layers = [...svg.matchAll(/<path[^>]*fill="(#[0-9a-fA-F]{6})"[^>]*\sd="([^"]+)"/g)].map(
    ([, fill, d]) => ({
      color: [1, 3, 5].map(i => parseInt(fill.slice(i, i + 2), 16)),
      contours: parseContours(d).map(c =>
        c.map(([x, y]) => [x * MARK_INSET + offset, y * MARK_INSET + offset])
      ),
    })
  )
  if (!layers.length) throw new Error(`no <path fill="#rrggbb" d="…"> found in ${MASTER}`)
  return layers
}

const LAYERS = readMaster()

/**
 * Coverage of every pixel of a `size` px image, as a value in 0..1 per pixel.
 *
 * Sampled on a 4x4 grid per pixel so edges antialias, but resolved a sample row
 * at a time — collecting the x where each edge crosses that row, then filling
 * the spans between them — rather than testing every sample against every edge,
 * which the traced contours have far too many of to afford. Even-odd fill: the
 * span between the 1st and 2nd crossing is inside, between the 2nd and 3rd
 * outside, and so on, which is what punches out the counters.
 */
function rasterize(contours, size, scale, samples = 4) {
  const coverage = new Float32Array(size * size)
  const weight = 1 / (samples * samples)
  const crossings = []

  for (let sy = 0; sy < size * samples; sy++) {
    const y = (sy + 0.5) / (samples * scale)
    crossings.length = 0
    for (const contour of contours) {
      for (let i = 0, j = contour.length - 1; i < contour.length; j = i++) {
        const [xi, yi] = contour[i]
        const [xj, yj] = contour[j]
        if (yi > y !== yj > y) crossings.push(((xj - xi) * (y - yi)) / (yj - yi) + xi)
      }
    }
    if (!crossings.length) continue
    crossings.sort((a, b) => a - b)

    const row = (sy / samples) | 0
    for (let k = 0; k + 1 < crossings.length; k += 2) {
      // Sample columns whose centre falls inside this span.
      const from = Math.max(0, Math.ceil(crossings[k] * scale * samples - 0.5))
      const to = Math.min(size * samples - 1, Math.floor(crossings[k + 1] * scale * samples - 0.5))
      for (let sx = from; sx <= to; sx++) coverage[row * size + ((sx / samples) | 0)] += weight
    }
  }
  return coverage
}

/** RGBA pixels for the icon at `size` px. */
function render(size, { rounded = true } = {}) {
  const scale = size / CANVAS
  const background = rasterize(plate(rounded), size, scale)
  const marks = LAYERS.map(layer => rasterize(layer.contours, size, scale))
  const pixels = Buffer.alloc(size * size * 4)

  for (let i = 0; i < size * size; i++) {
    const bg = Math.min(background[i], 1)
    if (bg === 0) continue
    // Paint the card, then each layer of the mark over it in document order.
    const rgb = [...CARD]
    marks.forEach((mark, layer) => {
      const fg = Math.min(mark[i], 1)
      if (fg === 0) return
      for (let c = 0; c < 3; c++) rgb[c] = rgb[c] * (1 - fg) + LAYERS[layer].color[c] * fg
    })
    const offset = i * 4
    for (let c = 0; c < 3; c++) pixels[offset + c] = Math.round(rgb[c])
    pixels[offset + 3] = Math.round(bg * 255)
  }
  return { size, pixels }
}

// --- PNG ---------------------------------------------------------------

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})

function crc32(buf) {
  let crc = 0xffffffff
  for (const byte of buf) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

function pngChunk(type, data) {
  const length = Buffer.alloc(4)
  length.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([length, body, crc])
}

function encodePng({ size, pixels }) {
  const header = Buffer.alloc(13)
  header.writeUInt32BE(size, 0)
  header.writeUInt32BE(size, 4)
  header[8] = 8 // bit depth
  header[9] = 6 // truecolour with alpha
  // Filter byte 0 (none) per scanline — these images are tiny and flat, so the
  // compression a predictor would buy is not worth the code.
  const raw = Buffer.alloc(size * (size * 4 + 1))
  for (let y = 0; y < size; y++) {
    pixels.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4)
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk('IHDR', header),
    pngChunk('IDAT', deflateSync(raw, { level: 9 })),
    pngChunk('IEND', Buffer.alloc(0)),
  ])
}

// --- ICO ---------------------------------------------------------------

/** One 32-bit BMP frame: bottom-up BGRA plus the legacy 1bpp AND mask. */
function icoFrame({ size, pixels }) {
  const maskStride = Math.ceil(size / 32) * 4
  const dib = Buffer.alloc(40)
  dib.writeUInt32LE(40, 0)
  dib.writeInt32LE(size, 4)
  dib.writeInt32LE(size * 2, 8) // colour data + mask, per the ICO convention
  dib.writeUInt16LE(1, 12)
  dib.writeUInt16LE(32, 14)
  dib.writeUInt32LE(size * size * 4 + maskStride * size, 20)

  const bgra = Buffer.alloc(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const from = (y * size + x) * 4
      const to = ((size - 1 - y) * size + x) * 4
      bgra[to] = pixels[from + 2]
      bgra[to + 1] = pixels[from + 1]
      bgra[to + 2] = pixels[from]
      bgra[to + 3] = pixels[from + 3]
    }
  }
  // Zeroed mask: the alpha channel already carries transparency, and every
  // renderer that understands 32bpp icons prefers it.
  return Buffer.concat([dib, bgra, Buffer.alloc(maskStride * size)])
}

function encodeIco(images) {
  const frames = images.map(icoFrame)
  const header = Buffer.alloc(6)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(frames.length, 4)

  let offset = 6 + frames.length * 16
  const entries = frames.map((frame, i) => {
    const entry = Buffer.alloc(16)
    entry[0] = images[i].size === 256 ? 0 : images[i].size
    entry[1] = entry[0]
    entry.writeUInt16LE(1, 4)
    entry.writeUInt16LE(32, 6)
    entry.writeUInt32LE(frame.length, 8)
    entry.writeUInt32LE(offset, 12)
    offset += frame.length
    return entry
  })

  return Buffer.concat([header, ...entries, ...frames])
}

// --- Output ------------------------------------------------------------

const write = (name, buffer) => {
  writeFileSync(path.join(OUT_DIR, name), buffer)
  console.log(`${name.padEnd(22)} ${buffer.length.toLocaleString()} bytes`)
}

/** The tab icon: the master mark, inset on the same rounded card. */
function faviconSvg() {
  const paths = LAYERS.map(layer => {
    const fill = '#' + layer.color.map(c => c.toString(16).padStart(2, '0')).join('')
    const d = layer.contours
      .map(c => 'M' + c.map(([x, y]) => `${x.toFixed(2)} ${y.toFixed(2)}`).join('L') + 'Z')
      .join('')
    return `  <path fill="${fill}" fill-rule="evenodd" d="${d}"/>`
  })
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" role="img" aria-label="Plenilo.com">
  <title>Plenilo.com</title>
  <rect width="64" height="64" rx="${CORNER_RADIUS}" fill="#fff"/>
${paths.join('\n')}
</svg>
`
}

write('favicon.svg', Buffer.from(faviconSvg()))
write('favicon.ico', encodeIco([16, 32, 48].map(size => render(size))))
write('apple-touch-icon.png', encodePng(render(180, { rounded: false })))
write('icon-192.png', encodePng(render(192)))
write('icon-512.png', encodePng(render(512)))
