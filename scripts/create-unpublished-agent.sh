#!/usr/bin/env bash
# Create an UNPUBLISHED Genie Agent as the promotion service principal, then grant
# the requesting developer CAN EDIT (build/curate/export — but NOT share/publish).
# Invoked by .github/workflows/create-genie-agent.yml. No PR, no approval.
set -euo pipefail

: "${AGENT_NAME:?agent_name required}"
: "${DEVELOPER_EMAIL:?developer_email required}"
WH="${GENIE_WAREHOUSE_ID:?set GENIE_WAREHOUSE_ID as a repo variable}"
PARENT="${GENIE_DEV_PARENT_PATH:-/Workspace/Shared/genie-dev}"
SEED_TABLE="${SEED_TABLE:-}"

# Minimal version-2 serialized space; seed one table if provided.
if [[ -n "$SEED_TABLE" ]]; then
  SS="{\"version\":2,\"data_sources\":{\"tables\":[{\"identifier\":\"${SEED_TABLE}\"}]}}"
else
  SS="{\"version\":2,\"data_sources\":{\"tables\":[]}}"
fi

# 1) Create the agent AS THE SP → the SP is the CAN MANAGE owner (the only publisher).
SPACE_ID=$(databricks genie create-space --json "$(jq -cn \
  --arg t "${AGENT_NAME} (draft)" \
  --arg d "Unpublished draft. Build here, then open a PR against resources/genie/ to publish." \
  --arg wh "$WH" --arg pp "$PARENT" --arg ss "$SS" \
  '{title:$t, description:$d, warehouse_id:$wh, parent_path:$pp, serialized_space:$ss}')" \
  -o json | jq -r '.space_id // .id')

echo "Created draft agent: ${SPACE_ID}"

# 2) Grant the developer CAN_EDIT (PATCH = additive; keeps the SP's CAN MANAGE).
#    CAN_EDIT can modify + export the agent but CANNOT change its sharing.
databricks permissions update genie "$SPACE_ID" --json "$(jq -cn \
  --arg u "$DEVELOPER_EMAIL" \
  '{access_control_list:[{user_name:$u, permission_level:"CAN_EDIT"}]}')"

echo "Granted CAN_EDIT to ${DEVELOPER_EMAIL}"
echo "Build it here: ${DATABRICKS_HOST%/}/genie/rooms/${SPACE_ID}"
echo "To publish: export it and open a PR — see README (Promote an agent)."
