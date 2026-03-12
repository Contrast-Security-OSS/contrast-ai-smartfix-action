# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

from src import contrast_api
from src.utils import debug_log, log


def reconcile_open_remediations(config, github_ops):
    """Checks all remediations the backend thinks are OPEN against actual GitHub PR state.

    Calls the appropriate backend transition for any that have drifted.
    Best-effort: logs warnings on failure, never raises, never exits.
    """
    try:
        open_remediations = contrast_api.get_open_remediations(
            contrast_host=config.CONTRAST_HOST,
            contrast_org_id=config.CONTRAST_ORG_ID,
            contrast_app_id=config.CONTRAST_APP_ID,
            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=config.CONTRAST_API_KEY,
        )
    except Exception as e:
        log(f"Error fetching open remediations: {e}", is_warning=True)
        return

    if not open_remediations:
        log("No open remediations to reconcile")
        return

    log(f"Found {len(open_remediations)} open remediation(s) to check")

    for rem in open_remediations:
        remediation_id = rem.get('remediationId', 'unknown')
        vuln_id = rem.get('vulnerabilityId', 'unknown')
        pr_number = rem.get('pullRequestNumber')

        try:
            if pr_number is None:
                log(f"Remediation {remediation_id} (vuln {vuln_id}) has no PR number, skipping", is_warning=True)
                continue

            actual_state = github_ops.get_pr_actual_state(pr_number)

            if actual_state is None:
                log(f"Could not determine state for PR #{pr_number} (remediation {remediation_id}), skipping", is_warning=True)
                continue

            if actual_state == 'OPEN':
                debug_log(f"Remediation {remediation_id} (vuln {vuln_id}, PR #{pr_number}): GitHub state is OPEN, no action needed")
                continue

            log(f"Reconciling remediation {remediation_id} (vuln {vuln_id}, PR #{pr_number}): GitHub state is {actual_state}, notifying backend")

            if actual_state == 'MERGED':
                contrast_api.notify_remediation_pr_merged(
                    remediation_id=remediation_id,
                    contrast_host=config.CONTRAST_HOST,
                    contrast_org_id=config.CONTRAST_ORG_ID,
                    contrast_app_id=config.CONTRAST_APP_ID,
                    contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                    contrast_api_key=config.CONTRAST_API_KEY,
                )
            elif actual_state == 'CLOSED':
                contrast_api.notify_remediation_pr_closed(
                    remediation_id=remediation_id,
                    contrast_host=config.CONTRAST_HOST,
                    contrast_org_id=config.CONTRAST_ORG_ID,
                    contrast_app_id=config.CONTRAST_APP_ID,
                    contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
                    contrast_api_key=config.CONTRAST_API_KEY,
                )
        except Exception as e:
            log(f"Error reconciling remediation {remediation_id} (vuln {vuln_id}, PR #{pr_number}): {e}", is_warning=True)
