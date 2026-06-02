#!/usr/bin/env bash
# Compatibility wrapper. Prefer scripts/deploy/setup-docker-ssl.sh.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/scripts/deploy/setup-docker-ssl.sh" "$@"
