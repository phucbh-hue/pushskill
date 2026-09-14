#!/usr/bin/env bash
set -euo pipefail

python -m pip install -r requirements.txt

GO_VERSION="1.24.6"
GO_ROOT="${HOME}/.local/go"
mkdir -p "${HOME}/.local" /tmp/go-download
curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -o /tmp/go-download/go.tar.gz
rm -rf "${GO_ROOT}"
tar -C "${HOME}/.local" -xzf /tmp/go-download/go.tar.gz
mv "${HOME}/.local/go" "${GO_ROOT}"
export PATH="${GO_ROOT}/bin:${HOME}/.local/bin:${PATH}"

npx -y @mvanhorn/printing-press-library@0.1.16 install arxiv --cli-only
npx -y @mvanhorn/printing-press-library@0.1.16 install techmeme --cli-only
npx -y @mvanhorn/printing-press-library@0.1.16 install trustpilot --cli-only