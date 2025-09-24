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

from enum import Enum


class FailureCategory(Enum):
    """Define failure categories as an enum to ensure consistency."""
    INITIAL_BUILD_FAILURE = "INITIAL_BUILD_FAILURE"
    EXCEEDED_QA_ATTEMPTS = "EXCEEDED_QA_ATTEMPTS"
    QA_AGENT_FAILURE = "QA_AGENT_FAILURE"
    GIT_COMMAND_FAILURE = "GIT_COMMAND_FAILURE"
    AGENT_FAILURE = "AGENT_FAILURE"
    GENERATE_PR_FAILURE = "GENERATE_PR_FAILURE"
    GENERAL_FAILURE = "GENERAL_FAILURE"
    EXCEEDED_TIMEOUT = "EXCEEDED_TIMEOUT"
    EXCEEDED_AGENT_EVENTS = "EXCEEDED_AGENT_EVENTS"
    INVALID_LLM_CONFIG = "INVALID_LLM_CONFIG"
