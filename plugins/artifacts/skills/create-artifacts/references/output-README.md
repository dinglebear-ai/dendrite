# Project Artifacts

Open `index.html` for the generated catalog, or use the `create-artifacts` skill's
`serve` command for local browsing. Run `inventory` for separate counts of
documents, scripts, datasets, evidence files, and model runs.

Artifacts live at `<owner-repo>/<type>/MM-DD-YY-description.*`. Bulk supporting
files live at `<owner-repo>/_evidence/<artifact-stem>/<run-id>/`. Plans have a
Markdown source and generated HTML. Export snapshots live under their repository's
`exports/` folder. Legacy symlinks preserve old citations; they are not duplicates.

Use `create-artifacts` to author and `review-artifacts` to assess content and
readiness. Unraid-related subjects always use Unraid templates. Every other new
artifact uses Aurora. The templates carry content scaffolds as well as styling;
the shared content contract and type guidance define the required information.

This README is a pointer to the maintained source in the Artifacts plugin under
`~/workspace/dendrite/plugins/artifacts`. The plugin owns templates, contracts,
skills, and reusable tools. Root guidance links do not create another source of
truth. Commit artifacts and evidence in this repository; update authoring rules
in Dendrite. A local artifact or export is not authorization to publish it.
