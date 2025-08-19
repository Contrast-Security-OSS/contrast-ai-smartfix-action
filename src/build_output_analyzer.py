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

def extract_build_errors(build_output):
    """
    Extract the most relevant error information from build output.

    This function captures error blocks with context before and after errors,
    and intelligently extends blocks when errors are found in sequence.

    Args:
        build_output: The complete output from the build command

    Returns:
        str: A condensed report of the most relevant error regions
    """
    # If output is small enough, just return it all
    if len(build_output) < 2000:
        return build_output

    lines = build_output.splitlines()

    # Look at the last part of the output (where errors typically appear)
    tail_lines = lines[-500:] if len(lines) > 500 else lines

    # Common error indicators across build systems
    error_indicators = ["error", "exception", "failed", "failure", "fatal"]

    # Process the lines to find error regions with their context
    context_size = 5  # Number of lines to include before an error
    error_regions = []  # Will hold start and end indices of error regions

    # First pass: identify all error lines
    error_line_indices = []
    for i, line in enumerate(tail_lines):
        line_lower = line.lower()
        if any(indicator in line_lower for indicator in error_indicators):
            error_line_indices.append(i)

    # Second pass: merge nearby errors into regions
    if error_line_indices:
        current_region_start = max(0, error_line_indices[0] - context_size)
        current_region_end = error_line_indices[0] + context_size

        for idx in error_line_indices[1:]:
            # If this error is within or close to current region, extend the region
            if idx - context_size <= current_region_end + 2:  # Allow small gaps
                current_region_end = idx + context_size
            else:
                # This error is far from the previous region, save current region
                # and start a new one
                error_regions.append((current_region_start, min(current_region_end, len(tail_lines) - 1)))
                current_region_start = max(0, idx - context_size)
                current_region_end = idx + context_size

        # Don't forget the last region
        error_regions.append((current_region_start, min(current_region_end, len(tail_lines) - 1)))

    # Extract the text from each error region
    error_blocks = []
    for start, end in error_regions:
        region_lines = tail_lines[start:end + 1]
        error_blocks.append("\n".join(region_lines))

    # If we found error blocks, return them (up to 3 most recent)
    if error_blocks:
        result_blocks = error_blocks[-3:] if len(error_blocks) > 3 else error_blocks
        return "BUILD FAILURE - KEY ERRORS:\n\n" + "\n\n...\n\n".join(result_blocks)

    # Fallback: just return the last part of the build output
    return "BUILD FAILURE - LAST OUTPUT:\n\n" + "\n".join(tail_lines[-50:])
