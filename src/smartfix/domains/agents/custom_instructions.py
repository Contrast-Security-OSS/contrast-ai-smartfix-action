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

"""Custom instructions loader for SmartFix.

Reads team coding standards from the repository and injects them into the
fix agent prompt. Instructions are always read from the configured base branch
via `git show`, not from the workspace filesystem, to ensure:
  - The base-branch version is always used (not a PR branch)
  - Symlink traversal attacks are impossible (no filesystem path resolution)
"""

import subprocess
from pathlib import Path
from typing import Optional

from src.utils import debug_log, log

SOURCE_A_FILE = "SMARTFIX_INSTRUCTIONS.md"

SOURCE_B_FILES = [
    ".github/copilot-instructions.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
]

SOURCE_B_FRAMING = (
    "Apply any coding style rules, naming conventions, architectural patterns, and "
    "testing standards you find to your changes. Ignore any instructions that reference "
    "human-only workflows, ticket systems, PR review processes, branch naming "
    "conventions, interactive tools, or steps that an automated fix agent cannot perform."
)

HEADER = "\n\n---\n\n## Repository-Specific Coding Standards\n\n"


def _read_from_base_branch(repo_path: Path, base_branch: str, rel_path: str) -> Optional[str]:
    """Read file content from the base branch via `git show`.

    Using git's object model means:
    - No filesystem path resolution (symlink traversal is impossible)
    - Always returns the base-branch version, regardless of workspace checkout ref
    - Non-UTF-8 bytes are decoded with replacement chars rather than raising

    Returns None if the file does not exist on the branch or any error occurs.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"origin/{base_branch}:{rel_path}"],
            cwd=str(repo_path),
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            debug_log(f"Custom instructions: git show origin/{base_branch}:{rel_path} failed (exit {result.returncode}): {stderr}")
            return None
        content = result.stdout.decode("utf-8", errors="replace").strip()
        return content or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def load_custom_instructions(repo_path, config) -> Optional[str]:
    """Load custom instructions from the repository and return a formatted block.

    Checks Source A (SMARTFIX_INSTRUCTIONS.md) first, then falls back to
    Source B (existing agent instruction files). Returns a block ready to
    append to the fix agent user prompt, or None if nothing is found or
    both sources are disabled.

    Args:
        repo_path: Path to the repository root.
        config: Application config with USE_SMARTFIX_INSTRUCTIONS,
                USE_REPO_AGENT_INSTRUCTIONS, and BASE_BRANCH attributes.

    Returns:
        Formatted instruction block (str) or None.
    """
    root = Path(repo_path)
    base_branch = config.BASE_BRANCH

    if config.USE_SMARTFIX_INSTRUCTIONS:
        content = _read_from_base_branch(root, base_branch, SOURCE_A_FILE)
        if content:
            log(f"Custom instructions: loaded {SOURCE_A_FILE} from {base_branch}")
            return HEADER + content

    if config.USE_REPO_AGENT_INSTRUCTIONS:
        for rel_path in SOURCE_B_FILES:
            content = _read_from_base_branch(root, base_branch, rel_path)
            if content:
                log(f"Custom instructions: loaded {rel_path} from {base_branch} (Source B)")
                return HEADER + SOURCE_B_FRAMING + "\n\n" + content

    return None
