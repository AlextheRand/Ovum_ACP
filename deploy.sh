#!/usr/bin/env bash
# Deploy ovum_mira custom component to HA server and reload
set -euo pipefail

REMOTE_PATH="ha:/config/custom_components/ovum_mira"

echo "→ Deploying custom_components/ovum_mira to ${REMOTE_PATH}..."
rsync -av --delete custom_components/ovum_mira/ "${REMOTE_PATH}/"
echo "✓ Deployed"

echo "→ Reloading HA config..."
TOKEN=$(cat ~/.ha_token)
curl -s -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "http://192.168.178.50:8123/api/services/homeassistant/reload_config_entry" \
  --data '{}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('✓ Reloaded' if d else '? No response')" \
  || echo "→ Manual reload required via HA UI (Config > Integrations > Ovum MIRA > Reload)"

echo "Done."
