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
# the applicable End User License Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#


"""
Directory Tree Utilities

Shared utilities for generating directory tree views of repositories.
Used by multiple agents (detection, fix, qa) to provide project structure context.
"""

import subprocess
from pathlib import Path
from typing import Optional

from src.utils import debug_log

# Directories excluded from tree output in both the tree CLI and the Python fallback.
EXCLUDED_DIRS = frozenset({"node_modules", "__pycache__", "target", "build", "dist", "venv"})

# Pattern used with tree -I to exclude hidden entries, compiled files, and common build dirs.
_TREE_EXCLUDE_PATTERN = "|".join([".*", "*.pyc"] + sorted(EXCLUDED_DIRS))


def _truncate_output(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending an informative suffix if truncated."""
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... [truncated, {len(text) - max_chars} chars omitted]"
    return text


def _filter_gitignored(repo_root: Path, items: list) -> list:
    """Return items with gitignored entries removed, using git check-ignore.

    Falls back to returning all items unchanged if git is unavailable or errors.
    """
    if not items:
        return items
    try:
        rel_paths = [str(item.relative_to(repo_root)) for item in items]
        result = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            input="\n".join(rel_paths),
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        # returncode 0: some paths ignored; 1: no paths ignored; other: error
        if result.returncode in (0, 1):
            ignored = set(result.stdout.splitlines())
            return [item for item in items if str(item.relative_to(repo_root)) not in ignored]
    except Exception:
        pass
    return items


def get_directory_tree(repo_root: Path, max_depth: int = 6, max_chars: int = 10000) -> str:
    """
    Generate a directory tree view of the project.

    Args:
        repo_root: Repository root directory
        max_depth: Maximum directory depth to show
        max_chars: Maximum characters to include (prevents context blowout)

    Returns:
        String representation of directory tree, or error message
    """
    try:
        # Try using tree command if available. --gitignore requires tree >= 2.0;
        # older versions will return non-zero and we fall through to the Python fallback.
        result = subprocess.run(
            ["tree", "-L", str(max_depth), "--dirsfirst", "--gitignore", "-I", _TREE_EXCLUDE_PATTERN],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return _truncate_output(result.stdout, max_chars)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: Generate simple tree manually
    try:
        tree_output = generate_simple_tree(repo_root, max_depth, repo_root=repo_root)
        return _truncate_output(tree_output, max_chars)
    except Exception as e:
        debug_log(f"Failed to generate directory tree: {e}")
        return "[Directory tree unavailable]"


def generate_simple_tree(
    path: Path,
    max_depth: int,
    current_depth: int = 0,
    prefix: str = "",
    repo_root: Optional[Path] = None,
) -> str:
    """
    Generate a simple directory tree manually.

    Args:
        path: Directory to traverse
        max_depth: Maximum depth to traverse
        current_depth: Current recursion depth
        prefix: Prefix for tree formatting
        repo_root: If provided, gitignored entries are excluded using git check-ignore.
                   Symlinked directories are never recursed into regardless of this setting.

    Returns:
        String representation of directory tree
    """
    if current_depth >= max_depth:
        return ""

    lines = []
    try:
        # Skip hidden files/directories and common build directories; dirs before files
        items = sorted(
            [
                item
                for item in path.iterdir()
                if not item.name.startswith(".") and item.name not in EXCLUDED_DIRS
            ],
            key=lambda x: (0 if x.is_dir() else 1, x.name),
        )

        if repo_root is not None:
            items = _filter_gitignored(repo_root, items)

        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            current_prefix = "└── " if is_last else "├── "
            lines.append(f"{prefix}{current_prefix}{item.name}")

            # Recurse into directories, but not symlinks (prevents circular symlink loops)
            if item.is_dir() and not item.is_symlink() and current_depth < max_depth - 1:
                extension = "    " if is_last else "│   "
                subtree = generate_simple_tree(
                    item, max_depth, current_depth + 1, prefix + extension, repo_root=repo_root
                )
                if subtree:
                    lines.append(subtree)

    except PermissionError:
        pass

    return "\n".join(lines)


def get_directory_tree_for_agent_prompt(repo_root: Path, max_depth: int = 6, max_chars: int = 10000) -> str:
    """
    Generate a formatted directory tree for inclusion in agent prompts.

    Returns formatted markdown section with header and code block.

    Args:
        repo_root: Repository root directory
        max_depth: Maximum directory depth to show
        max_chars: Maximum characters to include (prevents context blowout)

    Returns:
        Formatted markdown section with directory tree
    """
    tree = get_directory_tree(repo_root, max_depth, max_chars)
    return f"\n\n## Repository Directory Tree\n\n```\n{tree}\n```"
