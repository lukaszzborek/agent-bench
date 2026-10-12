# Shared template for benchmark trials. Optimizer tools are NOT baked in; they are installed per trial
# from tools/<name>/setup.sh according to the task's `arms:` block.
# Project toolchains come from templates/deps/<name>.sh, selected at build time via DEPS (see build-templates.sh).
ARG BASE=docker/sandbox-templates:claude-code
FROM ${BASE}
ARG DEPS=""
USER root
COPY deps/ /opt/bench-deps/
RUN for d in $DEPS; do echo "== dep $d" && bash "/opt/bench-deps/$d.sh"; done
USER agent
# The base image lags behind Claude Code releases; install the requested one (latest|stable|x.y.z) and keep it fixed,
# so a background update cannot change the agent in the middle of a run.
ARG CLAUDE_VERSION=""
ENV DISABLE_AUTOUPDATER=1
RUN if [ -n "$CLAUDE_VERSION" ] && command -v claude >/dev/null; then claude install --force "$CLAUDE_VERSION" && claude --version; fi
