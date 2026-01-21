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

"""
Command Detection Orchestrator

Coordinates two-phase detection approach:
- Phase 1: Deterministic detection (fast, file marker-based)
- Phase 2: LLM-based detection (iterative refinement with error feedback)
- Fallback: Returns NO_OP_BUILD_COMMAND when all phases fail

Always returns a command string - never None or raises exceptions.
"""

import logging
from pathlib import Path
from typing import Optional

from src.smartfix.config.command_detector import detect_build_command


logger = logging.getLogger(__name__)

# No-op build command constant for when detection fails
NO_OP_BUILD_COMMAND = "echo 'No build command detected - using no-op'"


def detect_build_command_with_fallback(
    repo_root: Path,
    project_dir: Optional[Path] = None,
    max_llm_attempts: int = 6,
    remediation_id: str = "unknown"
) -> str:
    """
    Detect build command using two-phase approach with guaranteed fallback.

    This orchestrates the complete detection workflow:
    1. Phase 1: Deterministic detection (file markers + --version checks)
    2. Phase 2: LLM-based detection (iterative refinement if Phase 1 fails)
    3. Fallback: Return NO_OP_BUILD_COMMAND if all phases fail

    Unlike the individual detection functions, this function ALWAYS returns
    a valid command string - it never returns None or raises exceptions.

    Args:
        repo_root: Repository root directory
        project_dir: Optional subdirectory for monorepo projects
        max_llm_attempts: Maximum LLM detection attempts (default: 6)
        remediation_id: For error tracking and telemetry (used in Phase 2)

    Returns:
        Valid build command string. Either:
        - Detected command from Phase 1 (deterministic)
        - Detected command from Phase 2 (LLM agent)
        - NO_OP_BUILD_COMMAND constant if both phases fail

    Examples:
        >>> detect_build_command_with_fallback(Path("/repo"))
        "mvn test"  # Phase 1 success

        >>> detect_build_command_with_fallback(Path("/unusual-repo"))
        "npm run custom-test"  # Phase 2 success

        >>> detect_build_command_with_fallback(Path("/no-markers"))
        "echo 'No build command detected - using no-op'"  # Fallback
    """
    # Phase 1: Deterministic Detection
    # Fast, file marker-based detection with security validation
    logger.info("Starting Phase 1: Deterministic build command detection")

    try:
        phase1_result = detect_build_command(repo_root, project_dir)
    except Exception as e:
        logger.error(f"Phase 1 detection failed with exception: {e}")
        phase1_result = None

    if phase1_result:
        # Phase 1 succeeded - return detected command
        logger.info(f"Phase 1 succeeded: Detected BUILD_COMMAND: {phase1_result}")
        return phase1_result

    # Phase 1 failed - log and proceed to Phase 2
    logger.warning("Phase 1 failed: Could not auto-detect BUILD_COMMAND from project structure")

    # Phase 2: LLM-based detection
    # TODO: Implement Phase 2 LLM detection integration
    # This will be implemented in beads contrast-ai-smartfix-action-6dp and 9yb
    #
    # When bead 6dp completes, Phase 1 will return (command, failed_attempts) tuple
    # The failed_attempts history should be passed to Phase 2 for context
    #
    # When implemented, this will:
    # 1. Collect build_files from project structure
    # 2. Initialize CommandDetectionAgent with max_llm_attempts and remediation_id
    # 3. Run iterative LLM detection with error feedback from Phase 1 failures
    # 4. Return detected command or None after max_attempts
    logger.info("Starting Phase 2: LLM-based build command detection")
    phase2_result = None  # Placeholder for Phase 2 implementation

    if phase2_result:
        # Phase 2 succeeded - return LLM-detected command
        logger.info(f"Phase 2 succeeded: Detected BUILD_COMMAND: {phase2_result}")
        return phase2_result

    # Both phases failed - return no-op fallback
    # This ensures callers always get a valid command string
    logger.warning(
        f"Both detection phases failed. Using no-op fallback: {NO_OP_BUILD_COMMAND}"
    )
    return NO_OP_BUILD_COMMAND
