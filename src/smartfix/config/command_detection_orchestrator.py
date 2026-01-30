# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
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

from pathlib import Path
from typing import Optional

from src.smartfix.config.command_detector import detect_build_command
from src.utils import log

# No-op build command constant for when detection fails
NO_OP_BUILD_COMMAND = "echo 'No build command detected - using no-op'"


def _collect_build_files(repo_root: Path, project_dir: Optional[Path] = None) -> list[str]:
    """
    Collect build configuration files from the project for LLM analysis.

    Args:
        repo_root: Repository root directory
        project_dir: Optional subdirectory for monorepo projects

    Returns:
        List of relative paths to build configuration files
    """
    search_dir = project_dir if project_dir else repo_root
    build_files = []

    markers = [
        'pom.xml', 'build.gradle', 'build.gradle.kts', 'package.json',
        'Makefile', 'pytest.ini', 'setup.py', 'pyproject.toml'
    ]

    for marker in markers:
        marker_path = search_dir / marker
        if marker_path.exists():
            rel_path = marker_path.relative_to(repo_root)
            build_files.append(str(rel_path))

    return build_files


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
    # File marker-based detection with actual build testing
    log("Starting Phase 1: Deterministic build command detection")

    try:
        phase1_command, phase1_failures = detect_build_command(
            repo_root,
            project_dir,
            remediation_id
        )
    except Exception as e:
        log(f"Phase 1 detection failed with exception: {e}", is_error=True)
        phase1_command = None
        phase1_failures = []

    if phase1_command:
        # Phase 1 succeeded - return detected command
        log(f"Phase 1 succeeded: Detected BUILD_COMMAND: {phase1_command}")
        return phase1_command

    # Phase 1 failed - log failure count and proceed to Phase 2
    if phase1_failures:
        log(
            f"Phase 1 failed: Tested {len(phase1_failures)} candidate(s), all failed. "
            "Proceeding to Phase 2 with failure history.",
            is_warning=True
        )
    else:
        log("Phase 1 failed: No suitable build commands found in project structure", is_warning=True)

    # Phase 2: LLM-based detection
    # Use LLM agent with filesystem access to analyze project and refine commands
    log("Starting Phase 2: LLM-based build command detection")

    try:
        # Lazy import to avoid circular dependency
        # (config → orchestrator → CommandDetectionAgent → sub_agent_executor → config)
        from src.smartfix.domains.agents.command_detection_agent import CommandDetectionAgent

        build_files = _collect_build_files(repo_root, project_dir)

        if build_files:
            log(f"Collected {len(build_files)} build file(s) for LLM analysis: {build_files}")
        else:
            log("No build files found - LLM will explore filesystem directly", is_warning=True)

        detection_agent = CommandDetectionAgent(
            repo_root=repo_root,
            project_dir=project_dir,
            max_attempts=max_llm_attempts
        )

        phase2_result = detection_agent.detect(
            build_files=build_files,
            failed_attempts=phase1_failures,
            remediation_id=remediation_id
        )
    except Exception as e:
        log(f"Phase 2 detection failed with exception: {e}", is_error=True)
        phase2_result = None

    if phase2_result:
        # Phase 2 succeeded - return LLM-detected command
        log(f"Phase 2 succeeded: Detected BUILD_COMMAND: {phase2_result}")
        return phase2_result

    # Both phases failed - return no-op fallback
    # This ensures callers always get a valid command string
    log(
        f"Both detection phases failed. Using no-op fallback: {NO_OP_BUILD_COMMAND}",
        is_warning=True
    )
    return NO_OP_BUILD_COMMAND
