# Build And Release Conventions

The rmcp family assumes host-level Cargo config for fast local builds. Do not add repo-local linker settings unless the repo has a documented exception.

Important conventions from `rmcp-template/docs/RUST.md`:

- Rust stable tracks the family MSRV/current stable policy.
- `mold`/`clang`, sccache, global job limits, and dev profile tuning live in `~/.cargo/config.toml`.
- Per-repo `.cargo/config.toml` is minimal: xtask alias and target-specific fallback only.
- Do not add `[target.x86_64-unknown-linux-gnu].rustflags` in repo config if it would shadow global mold flags.
- Windows release/cross-compile settings must avoid machine-specific `target-cpu=native`.

Current global Cargo baseline on Jacob's machines:

```toml
[build]
# Keep conservative for multiple concurrent agents. Solo builds can override.
jobs = 4
rustc-wrapper = "/home/jmagar/.local/bin/sccache-wrapper"

[env]
CARGO_PROFILE_DEV_CODEGEN_BACKEND = "llvm"
SCCACHE_SERVER_UDS = "/home/jmagar/.local/state/sccache/sccache.sock"

[unstable]
codegen-backend = true

[target.x86_64-unknown-linux-gnu]
linker = "clang"
rustflags = ["-C", "link-arg=-fuse-ld=mold"]

[profile.dev]
debug = 1
codegen-units = 8
split-debuginfo = "unpacked"
incremental = false
opt-level = 0

[profile.test]
debug = 1
codegen-units = 8

[profile.dev.package."*"]
opt-level = 1
```

Interpretation:

- `rustc -> clang -> mold`: `clang` is the linker driver; `-fuse-ld=mold`
  chooses the fast linker backend. Prefer this over `linker = "mold"`.
- Global `jobs = 4` is intentional for many simultaneous agent builds. For a
  solo local build on the current 20-logical-CPU host, override per command:

  ```bash
  CARGO_BUILD_JOBS=16 cargo build --release --locked --bin <name>
  CARGO_BUILD_JOBS=16 cargo build --profile release-fast --locked --bin <name>
  ```

- Do not make `jobs = 16` global unless the machine is dedicated to one build at
  a time.
- Cranelift is not the current default. The config keeps
  `CARGO_PROFILE_DEV_CODEGEN_BACKEND=llvm` because Cranelift-backed dev/test
  links have failed in aws-lc-backed binaries in this environment. Consider
  Cranelift only as a repo-specific experiment after verifying `cargo check`,
  `cargo test`, and any native TLS/aws-lc/ring paths.
- sccache is enabled through `/home/jmagar/.local/bin/sccache-wrapper`, not by
  pointing Cargo directly at `sccache`. The wrapper bypasses clippy, resolves
  rustup toolchain paths to stable version-pinned paths for sccache-dist safety,
  exports `SCCACHE_SERVER_UDS=/home/jmagar/.local/state/sccache/sccache.sock`, and then execs the
  mise-pinned `/home/jmagar/.local/sccache`.
- Some repos add a repo-local rustc wrapper for project-specific side effects.
  Axon's `.cargo/config.toml` points at `scripts/cargo-rustc-wrapper`, which
  delegates to sccache and copies completed `axon` binaries into local PATH.
  Keep that kind of install-copy behavior repo-local or explicitly opt-in; do
  not make it global for all Rust projects without a collision policy.

Use a repo-local fast release profile when the command should be portable across
CI, containers, and clean hosts. Example:

```toml
[profile.release-fast]
inherits = "release"
lto = false
codegen-units = 16
```

This keeps `opt-level = 3` from `release`, but skips whole-program ThinLTO and
lets the final crate codegen run with more parallelism. It is appropriate for
local deployable binaries and smoke testing. Keep full `release` for published
artifacts, benchmark-sensitive builds, and size-sensitive binaries.

Benchmark profile changes with warm rebuilds, not the first build of a new
profile:

```bash
touch src/main.rs
time CARGO_BUILD_JOBS=16 cargo build --profile release-fast --locked --bin <name>
touch src/main.rs
time CARGO_BUILD_JOBS=16 cargo build --release --locked --bin <name>
```

Release workflows attach built artifacts to GitHub Releases. Do not commit generated binaries or release tarballs back to `main`.
