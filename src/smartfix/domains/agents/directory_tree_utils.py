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
Directory Tree Utilities

Shared utilities for generating directory tree views of repositories.
Used by multiple agents (detection, fix, qa) to provide project structure context.
"""

import subprocess
from pathlib import Path

from src.utils import debug_log


def get_directory_tree(repo_root: Path, max_depth: int = 3, max_chars: int = 8000) -> str:
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
        # Try using tree command if available
        result = subprocess.run(
            ['tree', '-L', str(max_depth), '-I', 'node_modules|.git|__pycache__|*.pyc|.pytest_cache|.venv|venv|target|build|dist'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            tree_output = result.stdout
            # Truncate if too large to avoid blowing out context
            if len(tree_output) > max_chars:
                tree_output = tree_output[:max_chars] + f"\n... [truncated, {len(tree_output) - max_chars} chars omitted]"
            return tree_output
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: Generate simple tree manually
    try:
        tree_output = generate_simple_tree(repo_root, max_depth)
        # Truncate if too large
        if len(tree_output) > max_chars:
            tree_output = tree_output[:max_chars] + f"\n... [truncated, {len(tree_output) - max_chars} chars omitted]"
        return tree_output
    except Exception as e:
        debug_log(f"Failed to generate directory tree: {e}")
        return "[Directory tree unavailable]"


def generate_simple_tree(path: Path, max_depth: int, current_depth: int = 0, prefix: str = "") -> str:
    """
    Generate a simple directory tree manually.

    Args:
        path: Directory to traverse
        max_depth: Maximum depth to traverse
        current_depth: Current recursion depth
        prefix: Prefix for tree formatting

    Returns:
        String representation of directory tree
    """
    if current_depth >= max_depth:
        return ""

    lines = []
    try:
        # Get items, skip hidden and common build directories
        items = sorted([
            item for item in path.iterdir()
            if not item.name.startswith('.')
            and item.name not in {'node_modules', '__pycache__', 'target', 'build', 'dist', '.venv', 'venv'}
        ])

        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            current_prefix = "└── " if is_last else "├── "
            lines.append(f"{prefix}{current_prefix}{item.name}")

            # Recurse into directories
            if item.is_dir() and current_depth < max_depth - 1:
                extension = "    " if is_last else "│   "
                subtree = generate_simple_tree(item, max_depth, current_depth + 1, prefix + extension)
                if subtree:
                    lines.append(subtree)

    except PermissionError:
        pass

    return "\n".join(lines)


def get_directory_tree_for_agent_prompt(repo_root: Path, max_depth: int = 3, max_chars: int = 8000) -> str:
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
