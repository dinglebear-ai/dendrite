# Design and Template Parity

Both families provide all nine artifact types and retain the same evidence,
metadata, findings, exclusion, requirement, and lifecycle structures. Plans use
Markdown sources and the same task renderer; scripts are executable harness
templates. PR reports retain all six lifecycle stages and 29 registered sections.

## Unraid

The Unraid `_template` files are byte-preserved from the original artifact
repository. Their Inter/Source Code Pro typography, orange identity, severity
colors, structure, and light/dark behavior remain authoritative. The snapshot
hashes are in [design-provenance.json](design-provenance.json). Start from those
templates; never borrow Aurora tokens for Unraid output. Packaging fonts into an
output changes only their transport, not the typefaces or style values.

## Aurora

The Aurora family is based on the actual Aurora registry and the design system
used by Labby's Gateway Admin. Canonical source snapshots are recorded in
[design-provenance.json](design-provenance.json).

| Concern | Source | Artifact Use |
| --- | --- | --- |
| Tokens and theme | `registry/aurora/styles/aurora.css` | Navy surfaces, cyan/rose accents, semantic states, spacing, radii, motion |
| Typefaces | `registry/aurora/styles/aurora-fonts.css` | Manrope display, Inter body, JetBrains Mono code, Noto Sans fallback |
| Identity | `components/labby-brand.tsx` | Exact layered mark geometry and Aurora wordmark typography |
| Buttons | `registry/aurora/ui/button.tsx` and `aurora-components.css` | Compact controls with outlined accents and token-based focus states |
| Cards | `aurora-components.css` | Tiered gradient surfaces, borders, highlights, and shadows |
| Badges | `registry/aurora/ui/badge.tsx` | Semantic surface/border/foreground token families |
| Tables | `registry/aurora/ui/table.tsx` | Dense operator typography and semantic surfaces |
| Product reference | Labby `apps/gateway-admin/app/globals.css` | Operator UI context; Aurora remains the canonical template token source |

`assets/aurora/aurora.css` is the original token source. The HTML adapter maps
legacy structural class names to Aurora tokens so every type retains its
content structure. Static HTML implements those component styles without
requiring React or a running Labby instance. It does not claim to embed the
React component runtime.

Use Title Case for Aurora labels and headings, sentence case for body text,
and uppercase only for eyebrows and badges. Default to the canonical dark
theme; explicit light selection must use the canonical light tokens. Do not
introduce arbitrary palettes, typography, fabricated logos, or emoji icons.
Use the bundled mark, wordmark, and existing structural icons. Any additional
icon must come from Aurora's Lucide icon vocabulary, with an accessible label
where it conveys information.

Preserve dark/light contrast, reduced-motion behavior, readable code wrapping
or scrolling, native keyboard-operated details, and tables on narrow screens.
Body prose stays in Inter; monospace is reserved for code and identifiers.

## Updating the Snapshot

Update design resources deliberately against an inspected Aurora revision.
Record source paths, revision, hashes, and licensing notices; regenerate every
Aurora template and verify all nine types. Leave Unraid templates and existing
artifacts intact unless the user requests changes to them. Template families
are independently validated; cross-family token differences are intentional.
