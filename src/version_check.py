import os
import requests
from packaging.version import parse as parse_version, Version
from utils import debug_print

HEX_CHARS = "0123456789abcdef"
ACTION_REPO_URL = "https://github.com/Contrast-Security-OSS/contrast-ai-smartfix-action"

def normalize_version(version_str: str) -> str:
    """Normalize a version string for comparison by removing 'v' prefix."""
    if version_str and version_str.startswith('v'):
        return version_str[1:]
    return version_str

def safe_parse_version(version_str: str) -> Version:
    """Safely parse a version string, handling exceptions."""
    try:
        return parse_version(normalize_version(version_str))
    except Exception:
        return None

def get_latest_repo_version(repo_url: str):
    """Fetches the latest release tag from a GitHub repository."""
    try:
        # Clean the repo URL to avoid double https:// issues
        cleaned_repo_path = repo_url.replace('https://github.com/', '')
        if cleaned_repo_path == repo_url:
            # If no substitution happened, ensure we're using the correct format
            cleaned_repo_path = repo_url.replace('github.com/', '')
        
        # Construct the API URL for tags
        api_url = f"https://api.github.com/repos/{cleaned_repo_path}/tags"
        debug_print(f"Fetching tags from: {api_url}")
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        tags = response.json()

        if not tags:
            debug_print("No tags found in the repository.")
            return None

        valid_tags = []
        for tag in tags:
            try:
                version_str = tag['name']
                if version_str.startswith('v'):
                    version_str = version_str[1:]
                parse_version(version_str) # Check if it's a valid version
                valid_tags.append(tag['name'])
            except Exception:
                # Ignore tags that are not valid versions
                debug_print(f"Ignoring invalid version tag: {tag.get('name', 'unknown')}")
                pass

        if not valid_tags:
            debug_print("No valid version tags found in the repository.")
            return None

        # Sort valid tags to find the latest
        valid_tags.sort(key=lambda v: parse_version(v.lstrip('v')), reverse=True)
        debug_print(f"Latest version found: {valid_tags[0]}")
        return valid_tags[0]
    except requests.exceptions.RequestException as e:
        debug_print(f"Error fetching tags: {e}")
        return None
    except Exception as e:
        debug_print(f"An unexpected error occurred while fetching tags: {e}")
        return None

def check_for_newer_version(current_version, latest_version_str: str):
    """Compares the current version with the latest version.
    Returns the latest_version_str if it's newer, otherwise None.
    
    Args:
        current_version: Either a string version or a Version object
        latest_version_str: String representation of the latest version
        
    Returns:
        The latest_version_str if newer, otherwise None
    """
    original_latest_version_str = latest_version_str # Store the original

    try:
        # Handle the case where current_version is already a Version object
        if hasattr(current_version, 'release'):
            current_v = current_version
        else:
            # Handle string version
            current_v = parse_version(normalize_version(current_version))
            
        latest_v = parse_version(normalize_version(latest_version_str))

        debug_print(f"Comparing versions: current={current_v} latest={latest_v}")
        if latest_v > current_v:
            debug_print("Newer version detected")
            return original_latest_version_str # Return the original string
        debug_print("No newer version found")
        return None
    except Exception as e:
        debug_print(f"Error parsing versions for comparison: {current_version}, {latest_version_str} - {e}")
        return None

def do_version_check():
    """
    Orchestrates the version check:
    1. Gets the current action version from GitHub environment variables.
    2. Fetches the latest version from the repository.
    3. Compares versions and prints a message if a newer version is available.
    """
    debug_print("Starting version check")
    # Try several GitHub environment variables that might contain version info
    github_ref = os.environ.get("GITHUB_REF")
    github_action_ref = os.environ.get("GITHUB_ACTION_REF")
    github_sha = os.environ.get("GITHUB_SHA")
    
    # Log which environment variables are available
    debug_print("Available GitHub environment variables for version checking:")
    if github_ref:
        debug_print(f"  GITHUB_REF: {github_ref}")
    if github_action_ref:
        debug_print(f"  GITHUB_ACTION_REF: {github_action_ref}")
    if github_sha:
        debug_print(f"  GITHUB_SHA: {github_sha}")
    
    # Determine which reference to use (prefer GITHUB_ACTION_REF, fall back to GITHUB_REF)
    current_action_ref = github_action_ref or github_ref
    
    if not current_action_ref:
        if github_sha:
            debug_print(f"Running from SHA: {github_sha}. No ref found for version check, using SHA.")
            current_action_ref = github_sha
        else:
            debug_print("Warning: Neither GITHUB_ACTION_REF nor GITHUB_REF environment variables are set. Version checking is skipped.")
            return

    current_action_version = current_action_ref
    
    # Extract the version/tag name from refs/tags/v1.2.3 format
    if current_action_ref.startswith('refs/'):
        parts = current_action_ref.split('/')
        if len(parts) >= 3:
            current_action_version = parts[-1]
            debug_print(f"Extracted version from ref: {current_action_version}")
    
    # If we have a SHA (40 hex chars), skip version comparison
    if len(current_action_version) == 40 and all(c in HEX_CHARS for c in current_action_version.lower()):
        debug_print(f"Running action from SHA: {current_action_version}. Skipping version comparison against tags.")
        return
    
    # Try to parse the version
    parsed_version = safe_parse_version(current_action_version)
    if not parsed_version:
        # Check if we're running from a branch
        if current_action_ref.startswith('refs/heads/'):
            branch_name = current_action_version
            debug_print(f"Running from branch '{branch_name}'. Version checking is only meaningful when using release tags.")
        else:
            debug_print(f"Warning: Could not parse current action version '{current_action_version}' as a semantic version. Skipping version check.")
        return

    # Use original version string for display
    parsed_version_str_for_logging = current_action_version
    debug_print(f"Current action version: {parsed_version_str_for_logging}")

    # Fetch the latest version from the repository
    latest_repo_version = get_latest_repo_version(ACTION_REPO_URL)

    if latest_repo_version:
        debug_print(f"Latest version available in repo: {latest_repo_version}")
        newer_version = check_for_newer_version(parsed_version, latest_repo_version)
        if newer_version:
            # Use regular print for the new version message to ensure it's always shown
            print(f"INFO: A newer version of this action is available ({newer_version}).")
            print(f"INFO: You are running version {parsed_version_str_for_logging}.")
            print(f"INFO: Please update your workflow to use the latest version of the action like this: Contrast-Security-OSS/contrast-ai-smartfix-action@{newer_version}")
    else:
        debug_print("Could not determine the latest version from the repository.")
