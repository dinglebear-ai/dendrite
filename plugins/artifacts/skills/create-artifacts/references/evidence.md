# Evidence Storage

Human-facing artifacts stay in `<owner-repo>/<type>/MM-DD-YY-description.*`.
Bulk evidence belongs in `<owner-repo>/_evidence/<artifact-stem>/<run-id>/`.
The artifact stem includes the date and descriptive name. `_bundle.json` records
its stable artifact ID and path, run kind, producer, file paths, byte sizes, and
SHA-256 values. It is an index of bytes, not a claim that those bytes prove truth.

A new run contains `raw/` for captured input and observed output, and `derived/`
for analysis, extracted views, and model-generated results. Keep model chunks,
checkpoints, responses, reduction state, prompts, model identity/settings, input
hashes, failures, and outputs within that run. Mark it `--kind model-run`.
Do not present model-generated conclusions as independently observed evidence.

```sh
python3 "$SKILL_DIR/scripts/artifacts.py" evidence-start "$ARTIFACT" --kind model-run
# Write captures and derived results only inside the printed run directory.
python3 "$SKILL_DIR/scripts/artifacts.py" evidence-seal "$RUN" --producer "recorded tool or agent"
python3 "$SKILL_DIR/scripts/artifacts.py" evidence-verify "$RUN"
```

Seal after the run is complete. A sealed bundle is immutable; start a fresh run
for a retry or correction. Preserve failed attempts and distinguish them from
successful runs. Record actual argv/cwd/time/exit/revision in capture files using
the existing PR capture helpers when applicable. Sealing does not execute a
command, validate a source claim, or manufacture missing execution metadata.

Historical trees move intact beneath `legacy/` with a new ownership manifest.
Their internal formats, timestamps, observations, and file hashes remain
unchanged. Compatibility symlinks preserve previously recorded absolute paths.
Paired PR ledgers may remain beside their report to preserve the established
lifecycle contract; they are small authoritative metadata, not bulk raw output.
Shared repository evidence uses an explicit `_shared-*` owner rather than an
invented relationship to one artifact. Administrative receipts use `_system`.

`inventory` counts catalog items, documents, proof scripts, datasets, evidence
files, bundles, model runs, and export snapshots separately. The catalog does
not turn each evidence file into an artifact card. A fresh portable export
includes the evidence area and the owning artifacts; original sealed data stays
unchanged in the source repository.

`organize-evidence --plan FILE` inventories a proposed move. Review the mapping,
then run the same command with `--apply`. It checks the source hashes, refuses
existing destinations and symlink traversal, writes a receipt, and preserves old
links. Do not automatically delete, prune, compress, or deduplicate evidence.
Dependency environments, model weights, downloaded package caches, and disposable
build outputs belong outside this library; retain the information needed to
reproduce them in the run record.
