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

"""CODEOWNERS file parsing and reviewer resolution (TS-38988).

This module is SCM-agnostic: the CODEOWNERS convention is supported by
GitHub, GitLab, and Bitbucket. The parsing logic lives here, in the scm
domain, rather than in any platform-specific package.
"""

import fnmatch
from pathlib import Path
from typing import List, Optional, Set


_CODEOWNERS_LOCATIONS = [
    ".github/CODEOWNERS",
    "CODEOWNERS",
    "docs/CODEOWNERS",
]


def find_codeowners_file(repo_root: Path) -> Optional[Path]:
    """Return the path to the CODEOWNERS file in the repo, or None if absent.

    Searches in priority order: .github/CODEOWNERS, CODEOWNERS, docs/CODEOWNERS.
    """
    for relative in _CODEOWNERS_LOCATIONS:
        candidate = repo_root / relative
        if candidate.is_file():
            return candidate
    return None


def get_reviewers_for_files(changed_files: List[str], repo_root: Path) -> Set[str]:
    """Return the set of reviewer handles from CODEOWNERS that match any changed file.

    Parses the CODEOWNERS file (if present) and returns all owners whose patterns
    match at least one of the changed files. The @ prefix is stripped from each
    handle; team refs (e.g. org/team) are kept intact.

    Returns an empty set when no CODEOWNERS file exists or no patterns match.
    """
    codeowners_path = find_codeowners_file(repo_root)
    if codeowners_path is None:
        return set()

    entries = _parse_codeowners(codeowners_path)
    reviewers: Set[str] = set()

    for changed_file in changed_files:
        for pattern, owners in entries:
            if _matches(pattern, changed_file):
                reviewers.update(owners)

    return reviewers


def _parse_codeowners(path: Path) -> List[tuple]:
    """Parse a CODEOWNERS file into (pattern, owners) tuples.

    Skips blank lines and comment lines. Strips the leading @ from each owner.
    """
    entries = []
    for line in path.read_text().splitlines():
        line = line.split("#")[0].strip()  # strip inline comments and surrounding whitespace
        if not line:
            continue
        parts = line.split()
        pattern = parts[0]
        owners = [o.lstrip("@") for o in parts[1:]]
        if owners:
            entries.append((pattern, owners))
    return entries


def _matches(pattern: str, file_path: str) -> bool:
    """Return True if file_path matches the CODEOWNERS pattern.

    A leading / in the pattern is stripped before matching (root-anchored patterns
    like /docs/ or /src/*.py are treated the same as docs/ or src/*.py since
    file_path values never carry a leading slash).

    Handles three cases:
    - Directory pattern (ends with /): matches any file whose path starts with it
    - Pattern with no path separator: matches against basename anywhere in tree
    - Otherwise: full-path glob match
    """
    normalized_pattern = pattern[1:] if pattern.startswith("/") else pattern
    normalized_file_path = file_path.lstrip("/")
    if normalized_pattern.endswith("/"):
        return normalized_file_path.startswith(normalized_pattern)
    if "/" not in normalized_pattern:
        # Matches any file with that name/extension in any directory
        return fnmatch.fnmatch(normalized_file_path, normalized_pattern) or fnmatch.fnmatch(
            normalized_file_path.split("/")[-1], normalized_pattern
        )
    return fnmatch.fnmatch(normalized_file_path, normalized_pattern)
