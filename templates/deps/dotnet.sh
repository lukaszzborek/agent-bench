#!/usr/bin/env bash
# .NET SDK via official install script (Ubuntu 26.04 has no Microsoft apt feed). Pin channel here.
set -euo pipefail
CHANNEL="${DOTNET_CHANNEL:-10.0}"
apt-get update
apt-get install -y --no-install-recommends curl ca-certificates libicu-dev
rm -rf /var/lib/apt/lists/*
curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel "$CHANNEL" --install-dir /usr/share/dotnet
ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet
cat > /etc/profile.d/dotnet.sh <<'ENV'
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
ENV
dotnet --info | head -5
