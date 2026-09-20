# Shared template for benchmark trials. Optimizer tools are NOT baked in; they are installed per trial
# from tools/<name>/setup.sh according to the task's `arms:` block.
# Project toolchains come from templates/deps/<name>.sh, selected at build time via DEPS (see build-templates.sh).
ARG BASE
FROM ${BASE}
ARG DEPS=""
USER root
COPY deps/ /opt/bench-deps/
RUN for d in $DEPS; do echo "== dep $d" && bash "/opt/bench-deps/$d.sh"; done
USER agent
