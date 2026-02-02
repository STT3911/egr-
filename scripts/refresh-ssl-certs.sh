#!/bin/bash
# Copy Let's Encrypt certs to ./ssl (e.g. after renewal).
# Run from project root: ./scripts/refresh-ssl-certs.sh
set -e
cd "$(dirname "$0")/.."
echo "Copying SSL certs from Let's Encrypt to ./ssl..."
docker compose run --rm ssl-copy
echo "Done. Reload nginx to use new certs: docker compose exec egr-nginx nginx -s reload"
