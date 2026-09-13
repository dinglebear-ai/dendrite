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

### Visual comprehension contract

Aurora HTML artifacts are information interfaces, not decorated documents.
Their composition must make the outcome, confidence, severity, progress, and
proof boundaries visible before a reader parses the prose. Prefer compact
metrics, state indicators, status rails, diagrams, and progressive disclosure
when they replace repeated explanation without losing evidence.

Use Aurora color by meaning across the whole page: cyan for information and
navigation, mint for verified success, rose for risk and failure, amber for
caution and unknowns, and frost neutrals for supporting context. Do not tint
every surface. Reserve color for signals so it remains useful at a glance.

Keep display headings balanced and contained, with a practical maximum near
66px on wide screens and 44px on phones. Body lines should normally stay within
68 characters. Layout columns must use `minmax(0, …)` where long identifiers or
evidence could otherwise force overflow. Never allow narrow columns to turn
sentences into stacks of single words. Evidence and code scroll inside bounded
regions rather than widening the page.

Separate metric cards with space; do not use borders or pseudo-elements that
visually connect unrelated cards. Give each metric a semantic accent and enough
padding for its longest expected label. Every page region must earn its area:
remove repeated prose, collapse secondary evidence, and let the primary result
occupy the strongest visual position.

Use hover and focus feedback on interactive elements. Icon-only controls are
preferred when the icon is familiar and the surrounding context is clear; they
must expose an accessible name and a keyboard-accessible tooltip or popover.
Keep a text label when removing it would slow comprehension. Use transitions
for disclosure, selection, and direct manipulation, and provide an equivalent
reduced-motion state.

Before delivery, inspect a representative filled artifact at desktop and phone
widths. Check the top and bottom of every section, expanded details, the longest
title, every control and tooltip, code and evidence overflow, table behavior,
focus visibility, and reduced motion. A template scaffold alone is insufficient
visual proof because placeholder lengths do not represent real content.

### Aligned artifact families

Every Aurora HTML type shares the full-bleed identity bar, concise outcome hero,
semantic metric strip, icon vocabulary, sticky or compact wayfinding, accessible
disclosure and filtering, bounded evidence surfaces, responsive rules, and the
same token meanings. The primary visual story remains specific to the artifact:

| Type | Primary visual story | Secondary destination |
| --- | --- | --- |
| Reports | Findings, causal trace, and observed proof | Excluded claims |
| PR reports | Six-stage lifecycle readiness and evidence graph | Handoff state |
| Proposals | Recommendation and decision tradeoffs | Rejected alternatives |
| Specs | Requirements and acceptance checks | Explicit boundaries |
| Research | Confidence-weighted findings | Uncertainty and falsifiers |
| Sessions | Chronology, actions, and results | Open work and handoff |
| Docs | Durable rules and verification | Exceptions and non-goals |

Navigation must move between those meaningful regions or change the visible
information set. A control that produces no visible state change, useful empty
state, result count, or new destination is unfinished. Filters expose pressed
state and announce the visible record count. Zero-result filters explain what
is absent and offer a clear way back to the complete set.

## Updating the Snapshot

Update design resources deliberately against an inspected Aurora revision.
Record source paths, revision, hashes, and licensing notices; regenerate every
Aurora template and verify all nine types. Leave Unraid templates and existing
artifacts intact unless the user requests changes to them. Template families
are independently validated; cross-family token differences are intentional.
