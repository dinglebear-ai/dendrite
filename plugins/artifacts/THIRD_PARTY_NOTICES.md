# Source and Asset Notices

Aurora design tokens, identity components, and component adaptations originate
from `dinglebear-ai/aurora` at the revision recorded in the skill's
`references/design-provenance.json`. Original Aurora software is
AGPL-3.0-only except separately licensed third-party material. Its license is
included as `LICENSE`. Font notices are bundled under
`skills/create-artifacts/assets/fonts/licenses/` and embedded with authored HTML
fonts. These notices were retrieved from the respective `ofl/<family>/OFL.txt`
files in [Google Fonts](https://github.com/google/fonts/tree/main/ofl).

Manrope, Inter, Noto Sans, and JetBrains Mono are the canonical font files
provided by Aurora. The legacy Unraid templates use the existing packaged Inter
and Source Code Pro files from the artifact framework. Font files retain their
respective upstream licenses and attribution; the plugin does not relicense them.

The original artifact framework and Unraid templates were migrated from
`jmagar/artifacts` at the recorded revision. The preserved Unraid template
SHA-256 values establish their provenance. The plugin adopts these sources as
maintained project-owned runtime code, with changes reviewed and tested here.

Aurora source snapshots are updated deliberately; they are not fetched at
artifact-generation time. Derived static HTML components preserve the Aurora
visual contract without copying the Labby application runtime.
