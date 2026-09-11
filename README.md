# Genie Agents — create freely, publish via PR

**Anyone can create and build a Genie Agent. The reviewed pipeline below is the
sanctioned way to publish one (make it usable by analysts in Genie One).** The two
actions are deliberately different:

| Action | How | Gate | Who does it |
|---|---|---|---|
| **Create** a draft agent | `Create unpublished Genie Agent` workflow (manual trigger) | **None** — no PR | Any repo member |
| **Publish** an agent | Commit its definition → PR → merge | **PR approval (CODEOWNERS) + `bundle validate`** | Reviewers approve; SP deploys |

## How publishing works — and its honest limit

Publishing = sharing an agent with the analyst audience, and internal sharing
requires `CAN MANAGE`. The pipeline keeps the *sanctioned* publish path in one
identity: the **promotion service principal (SP)**. The Create workflow runs as the
SP (so sanctioned drafts are SP-owned and the developer gets only `CAN EDIT`), and
the Publish deploy runs as the SP and owns the production copies.

> [!WARNING] This is a process + monitoring gate, not a hard block
> There is **no separate create-agent permission** (confirmed via Glean, 2026-09-11):
> creating an agent needs the same Databricks SQL entitlement + warehouse `CAN USE`
> + `SELECT` that *building* one needs. So any developer who can build can also
> create their own agent, get `CAN MANAGE`, and share it directly — bypassing this
> pipeline. In a single workspace you **cannot prevent** that; you **detect and
> revert** it. Enforcement therefore rests on the monitoring below, not on the
> pipeline alone. (Hard prevention would need a dev workspace or restricting who can
> build — hard prevention would need a dev workspace or restricting who can build.)

## Enforcement (single workspace)

1. **Scheduled auto-unpublish reconciler (primary, shipped here).** The
   `reconcile_genie_shares` job (`resources/reconcile-shares.job.yml` +
   `src/reconcile_genie_shares.py`) runs every 15 min as the SP, enumerates Genie
   Agents, and **revokes the analyst-audience share from any agent the SP does not
   manage** — i.e. anything published by someone other than the SP. State-based and
   idempotent; ships with `dry_run=true` (logs only) until you validate, then flip to
   `false`. A real-time `system.access.audit` (`service_name='aibiGenie'`) alert is a
   fine complement, but this job is the control that actually reverts.
2. **Locked agent folders.** Genie agents **inherit permissions from their parent
   folder** (verified in e2-demo). Set `/Workspace/Shared/genie-dev` and
   `/genie-production` so only the SP has `CAN MANAGE` (admins always will too).
3. **No `CREATE SHARE` for developers** — closes the external OpenSharing/Delta
   Sharing path that `CAN_EDIT` would otherwise allow.
4. **Consumer UC grants scoped to gold tables** — a rogue draft on non-granted
   tables returns nothing.

## Create a draft agent (no PR)

Run the **Create unpublished Genie Agent** workflow (Actions → Run workflow):
`agent_name`, `developer_email`, optional `seed_table`. It creates the agent under
`/Workspace/Shared/genie-dev` as the SP, grants you `CAN EDIT`, and prints the URL.
Build and benchmark in the UI. Unshared → invisible in Genie One.

## Publish an agent (PR + merge)

1. Export your vetted draft:
   ```bash
   databricks genie get-space <DRAFT_SPACE_ID> --include-serialized-space -o json \
     | jq '.serialized_space | fromjson' > resources/genie/<name>.geniespace.json
   ```
2. Add `resources/genie/<name>.genie_space.yml` (copy `monetization.genie_space.yml`);
   its `permissions:` block shares to `genie-consumers`.
3. Open a PR. CI runs `bundle validate`; **CODEOWNERS** (`genie-reviewers`) review
   the data sources, instructions, and audience in the diff.
4. **Merge = publish.** CI deploys as the SP → a production copy (under
   `/Workspace/Shared/genie-production`) is created and shared with `genie-consumers`,
   live in Genie One. The published copy is SP-owned; the draft stays your sandbox.

## One-time setup

- **Groups (Okta → SCIM):** `genie-consumers` (audience), `genie-reviewers` (CODEOWNERS).
- **Promotion service principal:** workspace access, Databricks SQL entitlement,
  `CAN USE` warehouse, rights to create agents under both parent paths. M2M creds as
  GitHub secrets `DATABRICKS_HOST`/`DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET`;
  `GENIE_WAREHOUSE_ID` as a repo variable.
- **Agent folders:** create `/Workspace/Shared/genie-dev` and `/genie-production`,
  each with `CAN MANAGE` granted only to the SP (enforcement #2 above).
- **Developer population:** `CAN USE` warehouse + `SELECT` on data (to build), and
  **no `CREATE SHARE`** on the metastore (enforcement #3). Note: they inherently
  *can* create agents (no way to withhold that separately) — that's covered by the
  audit alert, not by an entitlement.
- **UC data grants:** run `sql/genie-consumers-grants.sql` for the gold tables.
- **Branch protection on `main`:** require PR, require CODEOWNERS review, require the
  `validate` check, no direct pushes.
- **Reconciler job:** set `automation_sp` (SP application ID) and `ops_email` in
  `databricks.yml`; the `reconcile_genie_shares` job deploys with the bundle. Confirm
  its dry-run output, then set its `dry_run` parameter to `false` (this is the real gate).
