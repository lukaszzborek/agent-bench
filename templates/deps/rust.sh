#!/usr/bin/env bash
# Rust stable via rustup from static.rust-lang.org (GitHub is blocked for the agent). Pin toolchain here.
set -euo pipefail
TOOLCHAIN="${RUST_TOOLCHAIN:-1.98.0}"
RUSTUP_VERSION="${RUSTUP_VERSION:-1.29.1}"
export RUSTUP_HOME=/opt/rust/rustup CARGO_HOME=/opt/rust/cargo
apt-get update
# libhwloc/libudev: iggy's server build scripts (hwlocality-sys) need them; rust-analyzer runs every build script of
# the workspace, so without them it loses build data for the whole of iggy
apt-get install -y --no-install-recommends curl ca-certificates build-essential pkg-config libssl-dev cmake \
  libhwloc-dev libudev-dev
rm -rf /var/lib/apt/lists/*
curl -sSfL -o /tmp/rustup-init \
  "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/x86_64-unknown-linux-gnu/rustup-init"
chmod +x /tmp/rustup-init
/tmp/rustup-init -y -q --no-modify-path --profile minimal --default-toolchain "$TOOLCHAIN" \
  -c clippy -c rustfmt -c rust-analyzer -c rust-src
rm /tmp/rustup-init
chmod -R a+rX /opt/rust
# Link the toolchain's binaries directly instead of the rustup proxies: they need no RUSTUP_HOME (su and login shells
# reset the env), ignore a repo's rust-toolchain.toml (a proxy would try to download another toolchain) and Serena
# falls back to rust-analyzer on PATH when there is no rustup. CARGO_HOME stays the per-user ~/.cargo (writable
# registry cache).
bin="$RUSTUP_HOME/toolchains/${TOOLCHAIN}-x86_64-unknown-linux-gnu/bin"
for b in "$bin"/*; do ln -sf "$b" "/usr/local/bin/$(basename "$b")"; done
cargo --version && rustc --version && cargo clippy --version && rustfmt --version && rust-analyzer --version
