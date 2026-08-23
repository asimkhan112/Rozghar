/**
 * Renders the Plenilo mark into the raster icon formats a browser asks for.
 *
 * `public/favicon.svg` is the master and covers every current browser, but a
 * tab icon is the one asset that still has to answer to old rules: Safari
 * before 17 and every Windows shell surface want an .ico, iOS wants a
 * non-transparent 180px PNG for the home screen, and Android reads the sizes
 * named in the web manifest. So the mark is described once, here, in the same
 * 64-unit coordinate space as the SVG, and each format is rendered from it —
 * which is what keeps the tab, the home screen and the install prompt showing
 * the same logo.
 *
 * Run after editing `public/favicon.svg`:  node tools/generate-favicons.mjs
 */

import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const OUT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../public')

const BRAND = [0x33, 0xa4, 0xbb]
const WHITE = [0xff, 0xff, 0xff]
const CANVAS = 64
const CORNER_RADIUS = 14

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

// "PL" — the same monogram the site header renders in its logo chip. The P is
// two contours: the letter, and the counter punched out of its bowl.
const LETTER_P = [
  [[12, 15], [20, 15], ...arc(20, 26, 11, -90, 90), [20, 49], [12, 49]],
  [[20, 20], ...arc(20, 26, 6, -90, 90), [20, 32]],
]
const LETTER_L = [[[36, 15], [44, 15], [44, 42], [53, 42], [53, 49], [36, 49]]]

/** Even-odd fill: a point inside an odd number of contours is inside the shape. */
function covers(contours, x, y) {
  let inside = false
  for (const contour of contours) {
    for (let i = 0, j = contour.length - 1; i < contour.length; j = i++) {
      const [xi, yi] = contour[i]
      const [xj, yj] = contour[j]
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
    }
  }
  return inside
}

/** Coverage of one pixel, sampled on a 4x4 grid so edges antialias. */
function coverage(contours, px, py, scale, samples = 4) {
  let hits = 0
  for (let sy = 0; sy < samples; sy++) {
    for (let sx = 0; sx < samples; sx++) {
      const x = (px + (sx + 0.5) / samples) / scale
      const y = (py + (sy + 0.5) / samples) / scale
      if (covers(contours, x, y)) hits++
    }
  }
  return hits / (samples * samples)
}

/** RGBA pixels for the mark at `size` px. */
function render(size, { rounded = true } = {}) {
  const scale = size / CANVAS
  const background = plate(rounded)
  const glyphs = [...LETTER_P, ...LETTER_L]
  const pixels = Buffer.alloc(size * size * 4)

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const bg = coverage(background, x, y, scale)
      const fg = Math.min(coverage(glyphs, x, y, scale), bg)
      const offset = (y * size + x) * 4
      if (bg === 0) continue
      for (let channel = 0; channel < 3; channel++) {
        // Composite white over the plate, then undo the premultiply: PNG and
        // BMP both store straight alpha.
        const premultiplied = BRAND[channel] * (bg - fg) + WHITE[channel] * fg
        pixels[offset + channel] = Math.round(premultiplied / bg)
      }
      pixels[offset + 3] = Math.round(bg * 255)
    }
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

write('favicon.ico', encodeIco([16, 32, 48].map(size => render(size))))
write('apple-touch-icon.png', encodePng(render(180, { rounded: false })))
write('icon-192.png', encodePng(render(192)))
write('icon-512.png', encodePng(render(512)))
