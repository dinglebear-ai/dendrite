# Legacy Artifact Migration

The migration preserves the original Git history and the original bytes of
authored artifacts and evidence. It files output under the artifact's subject
repository, moves framework ownership into this plugin, and records the exact
old/new path mapping and SHA-256 values in a dated migration receipt.

Old reports and plans may predate the repository and brand metadata now required
for new output. The receipt identifies them as historical artifacts rather than
silently modifying their claims or certification. Their dates come from
recorded artifact metadata, date-bearing names, or recorded filesystem dates,
with the fallback noted in the receipt.

The legacy location has compatibility links to the relocated output and plugin
resources. They contain no second copy of templates or artifacts. Sealed reports
and evidence continue to resolve their original absolute provenance paths.
The live catalog projects relative navigation through the migration map in
memory; portable export writes the projected links. Raw records remain unchanged.

Preserve archived records and evidence instead of rerunning historical commands
or claiming that old proofs still hold against current repositories. The catalog
reports historical validation failures separately in JSON using `historical`.
An expired worktree citation is a limitation of the old record, not grounds to
rewrite the old evidence. Future material changes use the report revision and
resealing workflow.

Reusable framework scripts and type guidelines are owned by the plugin.
Project-specific proof harnesses and captured measurement data remain artifacts.
Rebuildable environments and caches are retained in the migration backup,
outside the output catalog; they are not shipped in the plugin.

Do not delete the migration backup or compatibility links during routine
artifact creation. Removing those recovery paths is a separately scoped cleanup.
