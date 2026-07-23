# Unraid Community Applications plugin submission guide

This guide reconciles every artifact in `unraid/ci-runner-farm/community-applications` with the current CA contract. The worked folder supplies valuable release, copy, artwork, security, and testing lessons, but its legacy XML roots and fields are not the schema authority.

## Sources and precedence

Resolve conflicts in this order:

1. [Live submission help](https://ca.unraid.net/submit/help)
2. [Repository XML format](https://ca.unraid.net/submit/help/repository-xml), [profile format](https://ca.unraid.net/submit/help/repository-info-xml), and [parser-backed field reference](https://ca.unraid.net/submit/help/xml-field-reference)
3. [Maintained starter repository](https://github.com/unraid/unraid-community-apps-starter)
4. This guide
5. Worked or legacy repositories

## What to retain from every CI Runner Farm artifact

| Artifact | Retain | Modernize |
|---|---|---|
| `README.md` | Public artifact checks, published `.plg`, clean-system test, forum support, and pre-submission checklist | Submit the repository through the portal; run Validate and Scan instead of supplying legacy raw profile/template fields manually. |
| `DESCRIPTION.md` | One-liner, listing copy, forum BBCode, requirements, security disclosure, categories, and screenshot inventory | Keep the listing summary aligned with current `<Overview>`, not legacy `<Description>`. |
| `ca_profile.xml` | Profile, icon, forum/support, webpage, and real optional destinations | Put it at repository root with `<CommunityApplications>` as root and a non-empty `<Profile>`. |
| `ci-runner-farm.xml` | Name, `.plg` URL, support, project, category, artwork intent, and material risk disclosure | Use one current `<Plugin>` wrapper under `plugins/`; include only public parser-supported fields. |
| `ci-runner-farm.svg` | Editable square vector source and distinctive, small-size artwork | Replace the product-specific design; use the bundled SVG only as a dimensional scaffold. |
| `ci-runner-farm.png` | Inspect a 256×256 raster rendition | Current profile/plugin fields accept an icon URL; use SVG or PNG according to the live starter and verify it anonymously. |

## Hard gates

1. Keep the repository public and active.
2. Put an OSI-approved `LICENSE` at the repository root.
3. Put `ca_profile.xml` at the repository root with a non-empty `<Profile>`.
4. Publish the installable `.plg` and verify the exact `<PluginURL>` anonymously. A `releases/latest/download/<name>.plg` URL works only when every release attaches that stable filename.
5. Make all referenced icons, screenshots, project pages, and support pages public.
6. Provide a stable public support destination accepted by the current parser and keep it consistent with support metadata inside the `.plg` manifest. Prefer a dedicated Unraid forum thread, but do not treat `<Forum>` as required when an issue tracker or project help page is the maintained support surface.
7. Install the published artifact on a clean supported Unraid system and exercise install, configuration, update, and removal.

## Current repository layout

```text
repository-root/
├── LICENSE
├── README.md
├── ca_profile.xml
├── icon.svg
└── plugins/
    └── application-name.xml
```

Use `assets/plugin.xml.template` for each plugin wrapper. The current minimum is a `<Plugin>` root with exactly one direct `<Name>` and one direct `.plg` `<PluginURL>`. Treat every supported field as a direct singleton. Add accurate `<Overview>`, `<Support>`, `<Project>`, and `<Category>` for a useful, reviewable listing. The current parser-backed plugin catalog is `<PluginURL>`, `<Name>`, `<Category>`, `<Icon>`, `<Overview>`, `<Project>`, `<Support>`, `<Beta>`, `<Deprecated>`, `<DonateLink>`, `<DonateText>`, and `<ReadMe>`. Reject duplicate, nested, legacy, or invented fields instead of assuming the portal ignores them.

Use `assets/ca_profile.xml.template` at repository root. Keep `<CommunityApplications>` as the root and include exactly one direct, non-empty `<Profile>`. Treat every supported profile field as a direct singleton. The current profile catalog is `<Profile>`, `<Forum>`, `<WebPage>`, `<Icon>`, `<Discord>`, `<Facebook>`, `<Photo>`, `<Reddit>`, `<Twitter>`, `<Video>`, `<DonateLink>`, and `<DonateText>`. Add only real destinations.

For Docker applications, stop using this plugin-specific skill and follow the current `<Container version="2">` template.

## Copy and disclosure

Use `assets/DESCRIPTION.md.template` to keep the one-line value proposition, `<Overview>`, optional forum BBCode, requirements, categories, and screenshot inventory aligned. Keep the wrapper overview plain and readable.

Document material privilege, arbitrary-code execution, Docker socket access, host mounts, exposed secrets, and networking risk in user-visible project documentation, the maintained support destination, and the plugin install/configuration experience. The current public plugin wrapper fields do not include legacy `<Requires>` or `<Description>`, so do not hide essential warnings only in unsupported wrapper tags.

For self-hosted runners, explicitly explain root-equivalent implications of privileged Docker-in-Docker or socket access and prohibit untrusted public/fork pull-request workloads.

## Images

Use `assets/icon.svg.template` only as a dimensional scaffold. Keep artwork square and legible at listing size. When publishing PNG, render and inspect it at 256×256:

```bash
rsvg-convert -w 256 -h 256 icon.svg -o icon.png
```

Use real screenshots without secrets, tokens, private repository names, or identifying infrastructure. Load every raw URL anonymously.

## Pre-submission evidence

- Public, active repository and OSI-approved root license
- Root `ca_profile.xml` with non-empty profile
- Public `.plg` at the wrapper URL
- Authorized `--check-urls` preflight confirming that every wrapper `<PluginURL>` exactly matches the fetched `.plg` manifest's `pluginURL`, with DNS validation and IP-pinned TLS repeated across redirects
- Public support, project, artwork, and screenshot destinations
- Clean-system install, operation, update, and removal results
- Local preflight with all errors fixed and warnings reviewed
- Successful portal **Validate**, then **Scan**, after the final XML change
- Listing preview, security review, and explicit user approval before external submission

Plugin submissions are manually reviewed. Portal acceptance begins moderation; it does not prove safety, functionality, or publication.
