/**
 * Renders a plain-text job body as the structure it was written with.
 *
 * The description is one text column in the database, but an editor writes it
 * with headings, bullets and paragraph breaks — and dropping it into a single
 * `<p>` collapses every one of them into a wall of prose. This walks the
 * parsed blocks and emits the elements they describe, which also gives the
 * listing real headings and real lists for a screen reader and for search.
 */

import { color, radius, size, weight } from '@/design-system'
import { parseRichText } from '@/lib/richText'

export default function RichText({ text, fontSize }: { text: string; fontSize?: string }) {
  const blocks = parseRichText(text)
  if (!blocks.length) return null

  const body = fontSize ?? size.md

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {blocks.map((block, index) => {
        if (block.kind === 'heading')
          return (
            <h3
              key={index}
              style={{
                // Tight to what follows, generous above — the gap is what says
                // a new section started. Not on the first block, which already
                // sits under the card's own title.
                margin: index === 0 ? 0 : '6px 0 -4px',
                fontSize: size.md,
                fontWeight: weight.semibold,
                color: color.text.primary,
              }}
            >
              {block.text}
            </h3>
          )

        if (block.kind === 'list')
          return (
            <ul
              key={index}
              style={{
                margin: 0,
                paddingLeft: 0,
                listStyle: 'none',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {block.items.map((item, itemIndex) => (
                <li
                  key={itemIndex}
                  style={{
                    display: 'flex',
                    gap: 12,
                    alignItems: 'flex-start',
                    fontSize: body,
                    color: color.text.strong,
                    lineHeight: 1.6,
                  }}
                >
                  {block.ordered ? (
                    <span
                      style={{
                        flexShrink: 0,
                        minWidth: 18,
                        fontSize: size.sm,
                        fontWeight: weight.semibold,
                        color: color.brand.base,
                        lineHeight: 1.6,
                      }}
                    >
                      {itemIndex + 1}.
                    </span>
                  ) : (
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: radius.full,
                        background: color.brand.base,
                        flexShrink: 0,
                        // Centres the dot on the first line of the item.
                        marginTop: 8,
                      }}
                    />
                  )}
                  {item}
                </li>
              ))}
            </ul>
          )

        return (
          <p
            key={index}
            style={{
              margin: 0,
              fontSize: body,
              color: color.text.strong,
              lineHeight: 1.7,
              // Deliberate breaks inside a paragraph survive; the parser has
              // already rejoined the ones that were only hard wraps.
              whiteSpace: 'pre-line',
            }}
          >
            {block.text}
          </p>
        )
      })}
    </div>
  )
}
