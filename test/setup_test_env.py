"""Test environment helper utilities.

This module provides helper functions for test setup, including
temporary directory management and sample object factories.
"""

from pathlib import Path

from src.smartfix.domains.vulnerability import RemediationContext
from src.smartfix.domains.vulnerability.context import (
    PromptConfiguration, BuildConfiguration, RepositoryConfiguration
)
from src.smartfix.domains.vulnerability.models import Vulnerability, VulnerabilitySeverity


_SENTINEL = object()


def make_sample_context(
    remediation_id="sample-remediation",
    session_id="sample-session",
    fix_system_prompt="Fix system prompt",
    fix_user_prompt="Fix user prompt",
    build_config=_SENTINEL,
    build_command=None,
    user_build_command=None,
    user_format_command=None,
    repo_path="/tmp/test",
    language=None,
    vuln_uuid="sample-vuln-uuid",
    vuln_title="Sample Vulnerability",
    skip_writing_security_test=False,
) -> RemediationContext:
    """Build a real RemediationContext with sensible defaults for tests.

    Pass build_config=None to explicitly set no build configuration.
    Otherwise a BuildConfiguration is created from the build_command,
    user_build_command, and user_format_command arguments.
    """
    vulnerability = Vulnerability(
        uuid=vuln_uuid,
        title=vuln_title,
        rule_name="sample-rule",
        severity=VulnerabilitySeverity.HIGH,
    )
    prompts = PromptConfiguration(
        fix_system_prompt=fix_system_prompt,
        fix_user_prompt=fix_user_prompt,
    )
    if build_config is _SENTINEL:
        build_config = BuildConfiguration(
            build_command=build_command,
            user_build_command=user_build_command,
            user_format_command=user_format_command,
        )
    repo_config = RepositoryConfiguration(
        repo_path=repo_path,
        base_branch="main",
    )
    return RemediationContext(
        remediation_id=remediation_id,
        vulnerability=vulnerability,
        prompts=prompts,
        build_config=build_config,
        repo_config=repo_config,
        skip_writing_security_test=skip_writing_security_test,
        session_id=session_id,
        language=language,
    )


def create_temp_repo_dir():
    """
    Create a temporary directory for repository testing.

    Returns:
        pathlib.Path: Path to temporary directory
    """
    import tempfile
    return Path(tempfile.mkdtemp())


def cleanup_temp_dir(temp_dir):
    """
    Clean up temporary directory.

    Args:
        temp_dir: Path to temporary directory to clean up
    """
    import shutil
    if temp_dir and temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
