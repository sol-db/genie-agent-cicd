# Databricks notebook source
# =============================================================================
# Genie share reconciler  (enforcement control #1 — the auto-unpublish job)
# =============================================================================
# Keeps ONLY service-principal-published agents shared with the analyst audience.
# Any Genie Agent that is shared to the audience but is NOT managed by the promotion
# SP is treated as "published by someone other than the SP" and is UNPUBLISHED (its
# audience share is revoked). This is the periodic backstop that makes the single-
# workspace model authoritative — because the platform can't hard-block a developer
# from sharing their own agent (create == build), we detect and revert it here.
#
# State-based on purpose: it reads the CURRENT sharing state rather than parsing the
# audit log, so it doesn't depend on any audit-event schema and is fully idempotent.
# (A real-time audit alert on aibiGenie permission events is a fine complement, but
#  this scheduled job is the control that actually reverts.)
#
# SAFETY: dry_run defaults to "true" — it only logs what it WOULD unpublish. Validate
# the output, then set the job parameter dry_run=false to enforce.
#
# The sanctioned test = "the SP is a direct CAN_MANAGE grantee." Legit published
# agents are created by the SP (deploy identity) so the SP manages them; a developer-
# created agent has the developer as manager, not the SP. Workspace admins always
# retain (inherited) CAN_MANAGE — that's expected and never touched.

# COMMAND ----------
%pip install --quiet databricks-sdk
dbutils.library.restartPython()

# COMMAND ----------
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import iam


def param(name, default):
    try:
        return dbutils.widgets.get(name)
    except Exception:
        return default


# SP identity AS IT APPEARS IN ACLs. For a service principal this is its application
# ID (matched against service_principal_name). Confirm the exact string with a dry run.
SP_IDENTITY = param("sp_identity", "")
CONSUMER_GROUP = param("consumer_group", "genie-consumers")
DRY_RUN = param("dry_run", "true").lower() == "true"

# Groups that mean "visible to analysts in Genie One". Include the all-account-users
# group as it appears in your workspace (commonly "account users" and/or "users").
AUDIENCE_GROUPS = {CONSUMER_GROUP, "account users", "users"}

assert SP_IDENTITY, "sp_identity parameter is required (the SP application ID)"

w = WorkspaceClient()


def direct_levels(acl):
    """Permission levels granted DIRECTLY on the object (ignore inherited)."""
    return {p.permission_level.value if hasattr(p.permission_level, "value") else p.permission_level
            for p in (acl.all_permissions or []) if not p.inherited}


def sp_manages(acls):
    for a in acls:
        principal = a.service_principal_name or a.user_name or getattr(a, "display_name", None)
        if principal == SP_IDENTITY and "CAN_MANAGE" in direct_levels(a):
            return True
    return False


checked, flagged = 0, []
for space in w.genie.list_spaces():          # SDK paginates
    sid = space.space_id
    checked += 1
    perms = w.permissions.get(request_object_type="genie", request_object_id=sid)
    acls = perms.access_control_list or []

    # "Published" = a real direct grant (beyond default CAN_READ) to an audience group.
    published = [a for a in acls if a.group_name in AUDIENCE_GROUPS and (direct_levels(a) - {"CAN_READ"})]
    if not published:
        continue
    if sp_manages(acls):
        continue  # sanctioned: the SP published it — leave it live

    # Non-SP publication → rebuild the ACL without the audience grants (unpublish).
    keep = []
    for a in acls:
        lvls = direct_levels(a)
        if not lvls:
            continue                      # only inherited — leave to inheritance
        if a.group_name in AUDIENCE_GROUPS:
            continue                      # drop the audience share
        for lvl in lvls:
            keep.append(iam.AccessControlRequest(
                group_name=a.group_name,
                user_name=a.user_name,
                service_principal_name=a.service_principal_name,
                permission_level=iam.PermissionLevel(lvl),
            ))

    flagged.append((sid, space.title))
    print(f"UNPUBLISH  {sid}  '{space.title}'  — audience share not made by the SP")
    if not DRY_RUN:
        w.permissions.set(request_object_type="genie", request_object_id=sid, access_control_list=keep)
        print(f"           {sid}  audience share revoked")

mode = "(dry-run) would unpublish" if DRY_RUN else "unpublished"
print(f"\nChecked {checked} space(s); {mode} {len(flagged)}.")
if flagged and DRY_RUN:
    print("Review the list above, then set the job parameter dry_run=false to enforce.")
