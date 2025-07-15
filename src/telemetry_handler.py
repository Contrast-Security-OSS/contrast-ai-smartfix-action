#-
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security’s commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import config # To access VERSION and other config values as needed

# Initialize the global telemetry data object
# This will be populated throughout the script's execution.
_telemetry_data = {}
_pre_init_log_buffer = [] # Temporary buffer for logs before full initialization
_telemetry_initialized = False # Flag to indicate if initialize_telemetry has run

def reset_vuln_specific_telemetry():
    """
    Resets vulnerability-specific telemetry fields to None or empty states.
    This should be called when starting analysis for a new vulnerability.
    """
    global _telemetry_data
    if not _telemetry_data:
        return # Telemetry not initialized yet

    _telemetry_data["vulnInfo"]["vulnId"] = None
    _telemetry_data["vulnInfo"]["vulnRule"] = None
    _telemetry_data["appInfo"]["programmingLanguage"] = None
    _telemetry_data["appInfo"]["technicalStackInfo"] = None
    _telemetry_data["appInfo"]["frameworksAndLibraries"] = []
    _telemetry_data["resultInfo"]["prCreated"] = False
    _telemetry_data["resultInfo"]["confidence"] = None
    _telemetry_data["resultInfo"]["filesModified"] = 0
    _telemetry_data["resultInfo"]["aiSummaryReport"] = None
    _telemetry_data["additionalAttributes"]["remediationId"] = None
    _telemetry_data["agentEvents"] = []

def initialize_telemetry():
    """
    Initializes the telemetry data structure with default and placeholder values.
    This should be called once at the beginning of the main script.
    Args:
        initial_config_dict: A dictionary representation of the config module's settings.
    """
    global _telemetry_data, _pre_init_log_buffer, _telemetry_initialized

    _telemetry_data = {
        "teamServerHost": config.CONTRAST_HOST,
        "vulnInfo": {
            "vulnId": None, 
            "vulnRule": None
        },
        "appInfo": {
            "programmingLanguage": None, 
            "technicalStackInfo": None,  
            "frameworksAndLibraries": [] 
        },
        "configInfo": {
            "sanitizedBuildCommand": config.BUILD_COMMAND, 
            "buildCommandRunTestsIncluded": False,
            "sanitizedFormatCommand": config.FORMATTING_COMMAND, 
            "aiProvider": None, 
            "aiModel": None     
        },
        "resultInfo": {
            "prCreated": False, 
            "confidence": None, 
            "filesModified": 0, 
            "aiSummaryReport": None 
        },
        "agentEvents": [], 
        "additionalAttributes": {
            "fullLog": "", 
            "scriptVersion": config.VERSION, 
            "remediationId": None, # Populated when remediation ID is known
        }
    }
    
    agent_model = config.AGENT_MODEL
    if agent_model:
        parts = agent_model.split('/', 1)
        _telemetry_data["configInfo"]["aiProvider"] = parts[0]
        if len(parts) > 1:
            _telemetry_data["configInfo"]["aiModel"] = parts[1]
        else:
            _telemetry_data["configInfo"]["aiModel"] = parts[0]

    # Process any buffered log messages
    if _pre_init_log_buffer:
        buffered_log_content = "\n".join(_pre_init_log_buffer)
        _telemetry_data["additionalAttributes"]["fullLog"] = buffered_log_content
        _pre_init_log_buffer = [] # Clear the buffer
    
    _telemetry_initialized = True

def get_telemetry_data():
    """
    Returns a copy of the current telemetry data object that is JSON serializable.
    
    Behavior based on ENABLE_FULL_TELEMETRY setting:
    - When True (default): Sends the full log data without truncation, along with all other telemetry fields.
      The backend service has been confirmed to handle complete log data to aid in debugging and analysis.
    - When False: Excludes the fullLog field entirely and omits sensitive command fields.
    
    As of June 2025, the previous 20KB limit for logs has been removed, and either the full log is sent
    or no log is sent, based on the ENABLE_FULL_TELEMETRY setting.
    """
    import copy
    import re
    
    # Make a deep copy to ensure we're not modifying the original
    telemetry_copy = copy.deepcopy(_telemetry_data)
    
    # Helper function to make sure all values are JSON serializable
    def ensure_json_serializable(obj):
        if isinstance(obj, dict):
            return {k: ensure_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [ensure_json_serializable(item) for item in obj]
        elif callable(obj):  # If it's a function or method
            return str(obj)  # Convert to string representation
        elif obj is None or isinstance(obj, (str, int, float, bool)):
            return obj  # Already serializable types
        else:
            # Convert any other type to string
            return str(obj)
    
    # Helper function to truncate a string to a maximum size
    def truncate_text(text, max_length, keep_end=False):
        if not text or len(text) <= max_length:
            return text
            
        if keep_end:
            # Keep the end of the text (useful for logs)
            return f"...[{len(text) - max_length} chars truncated]...\n{text[-max_length:]}"
        else:
            # Keep the beginning of the text (useful for reports/summaries)
            return f"{text[:max_length-50]}...[truncated, {len(text) - max_length} chars removed]"
            
    # Helper function to truncate large text fields within nested structures
    def truncate_large_text_fields(obj, max_length=1500):
        if isinstance(obj, dict):
            for key, value in obj.items():
                # Skip fullLog entirely - we want to preserve its full content
                if key == "fullLog":
                    continue
                    
                if isinstance(value, str) and len(value) > max_length:
                    # Most text fields should keep the beginning (more important info)
                    obj[key] = truncate_text(value, max_length, keep_end=False)
                elif isinstance(value, (dict, list)):
                    truncate_large_text_fields(value, max_length)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, (dict, list)):
                    truncate_large_text_fields(item, max_length)
        return obj
    
    # Make the entire telemetry data structure JSON serializable
    telemetry_copy = ensure_json_serializable(telemetry_copy)
    
    # Field-specific size limits - tailored to the database column sizes
    field_limits = {
        "aiSummaryReport": 250,        # 250 chars for aiSummaryReport (VARCHAR(255) in DB)
        "llmAction.summary": 1000,     # 1KB for LLM action summaries
        "defaultTextLength": 1500      # 1.5KB default for any other text field
    }
    
    # Special handling for aiSummaryReport - it gets its own smaller size limit
    if "resultInfo" in telemetry_copy and "aiSummaryReport" in telemetry_copy["resultInfo"]:
        summary = telemetry_copy["resultInfo"]["aiSummaryReport"]
        if summary:  # Only process if not None or empty
            if len(summary) > field_limits["aiSummaryReport"]:
                # Simple truncation for aiSummaryReport to maximize useful content within VARCHAR(255) constraint
                telemetry_copy["resultInfo"]["aiSummaryReport"] = summary[:field_limits["aiSummaryReport"]-3] + "..."
    
    # Process all agent events and other nested text fields with more conservative limits
    truncate_large_text_fields(telemetry_copy, field_limits["defaultTextLength"])
    
    # Control what telemetry data is sent based on ENABLE_FULL_TELEMETRY setting
    if not config.ENABLE_FULL_TELEMETRY:
        # When full telemetry is disabled:
        # 1. Remove sensitive command fields
        if "configInfo" in telemetry_copy:
            telemetry_copy["configInfo"] = telemetry_copy["configInfo"].copy()
            telemetry_copy["configInfo"]["sanitizedBuildCommand"] = ""
            telemetry_copy["configInfo"]["sanitizedFormatCommand"] = ""
        
        # 2. Remove the fullLog entirely
        if "additionalAttributes" in telemetry_copy and "fullLog" in telemetry_copy["additionalAttributes"]:
            telemetry_copy["additionalAttributes"] = telemetry_copy["additionalAttributes"].copy()
            telemetry_copy["additionalAttributes"].pop("fullLog", None)

    # Debug: Print the JSON structure with key info about size
    import json
    debug_copy = copy.deepcopy(telemetry_copy)
    
    # Replace large text fields with size info for debug output
    if "additionalAttributes" in debug_copy and "fullLog" in debug_copy["additionalAttributes"]:
        full_log = debug_copy["additionalAttributes"]["fullLog"]
        log_size_kb = len(full_log) / 1024
        debug_copy["additionalAttributes"]["fullLog"] = f"[Full log included, size: {log_size_kb:.2f}KB, {len(full_log)} chars]"
    
    if "resultInfo" in debug_copy and "aiSummaryReport" in debug_copy["resultInfo"] and debug_copy["resultInfo"]["aiSummaryReport"]:
        summary = debug_copy["resultInfo"]["aiSummaryReport"]
        debug_copy["resultInfo"]["aiSummaryReport"] = f"[Summary truncated, total length: {len(summary)} chars]"
        
    # Calculate total size of the JSON payload
    json_data = json.dumps(debug_copy, default=str)
    json_size_kb = len(json_data) / 1024
    
    from utils import debug_log
    
    # Adjust debug message based on whether fullLog is being sent
    if config.ENABLE_FULL_TELEMETRY:
        debug_log(f"Telemetry payload size: {json_size_kb:.2f}KB (fullLog is being sent in its entirety)")
    else:
        debug_log(f"Telemetry payload size: {json_size_kb:.2f}KB (fullLog is excluded per ENABLE_FULL_TELEMETRY=false setting)")
    # Uncomment the following line if you need to see the full structure
    # debug_log(json.dumps(debug_copy, indent=2, default=str))

    return telemetry_copy

def update_telemetry(key_path: str, value):
    """
    Updates a specific field in the telemetry data using a dot-separated key path.
    Example: update_telemetry("vulnInfo.vulnId", "CVE-1234")
    """
    global _telemetry_data
    keys = key_path.split('.')
    data_ptr = _telemetry_data
    for i, key in enumerate(keys):
        if i == len(keys) - 1:
            data_ptr[key] = value
        else:
            # Ensure intermediate dictionaries exist, especially for nested structures like additionalAttributes
            if key not in data_ptr or not isinstance(data_ptr.get(key), dict):
                data_ptr[key] = {}
            data_ptr = data_ptr[key]

def add_log_message(message: str):
    """
    Appends a message to the fullLog in telemetry or to a pre-init buffer.
    Ensures messages are separated by newlines in the log.
    """
    global _telemetry_data, _pre_init_log_buffer, _telemetry_initialized

    if not _telemetry_initialized:
        _pre_init_log_buffer.append(message)
    else:
        # Ensure additionalAttributes and fullLog exist and are initialized correctly
        # This check becomes more robust if initialize_telemetry guarantees these paths
        if "additionalAttributes" not in _telemetry_data:
            _telemetry_data["additionalAttributes"] = {}
        
        current_log = _telemetry_data["additionalAttributes"].get("fullLog")
        if current_log:
            _telemetry_data["additionalAttributes"]["fullLog"] = current_log + "\n" + message
        else:
            _telemetry_data["additionalAttributes"]["fullLog"] = message

def add_agent_event(event_data: dict):
    """Appends a new agent event to the agentEvents list."""
    global _telemetry_data
    _telemetry_data["agentEvents"].append(event_data)

def create_ai_summary_report(pr_body: str) -> str:
    """
    Creates a concise summary for aiSummaryReport from the PR body content.
    Extracts the most important information while keeping the result under the
    VARCHAR(255) constraint of the database field.

    Args:
        pr_body: The full PR body content

    Returns:
        str: A concise summary optimized for the aiSummaryReport field
    """
    import re
    
    # Extract the first heading as the primary fix description
    first_heading_match = re.search(r'##\s+(.*?)$', pr_body, re.MULTILINE)
    first_heading = first_heading_match.group(1).strip() if first_heading_match else "Fix applied"
    
    # Get a brief excerpt from the vulnerability summary section
    vuln_summary_match = re.search(r'## Vulnerability Summary\s+(.*?)(?=##|\Z)', pr_body, re.DOTALL)
    vuln_summary = ""
    if vuln_summary_match:
        # Extract the first sentence or up to 80 chars from vulnerability summary
        vuln_text = vuln_summary_match.group(1).strip()
        first_sentence = re.match(r'([^.!?]*[.!?])', vuln_text)
        if first_sentence:
            vuln_summary = first_sentence.group(1).strip()
        else:
            vuln_summary = vuln_text[:80].strip()
    
    # Extract fix summary if available
    fix_summary = ""
    fix_match = re.search(r'## Fix Summary\s+(.*?)(?=##|\Z)', pr_body, re.DOTALL)
    if fix_match:
        # Get just the first sentence or phrase of the fix summary
        fix_text = fix_match.group(1).strip()
        first_sentence = re.match(r'([^.!?]*[.!?])', fix_text)
        if first_sentence:
            fix_summary = first_sentence.group(1).strip()
        else:
            fix_summary = fix_text[:50].strip()
    
    # Construct a concise summary with the most important elements
    # Format: "Heading: Vulnerability info | Fix approach"
    max_summary_length = 245  # Leave a small margin below 255
    
    # Start with the heading
    summary_parts = [first_heading]
    
    # Add vulnerability info if we have space
    if vuln_summary and (len(first_heading) + len(vuln_summary) + 2) <= max_summary_length:
        summary_parts.append(vuln_summary)
    
    # Add fix approach if we still have space
    if fix_summary and (len(": ".join(summary_parts)) + len(fix_summary) + 3) <= max_summary_length:
        summary_parts.append(fix_summary)
    
    # Join the parts with appropriate separators
    if len(summary_parts) == 1:
        brief_summary = summary_parts[0]
    elif len(summary_parts) == 2:
        brief_summary = f"{summary_parts[0]}: {summary_parts[1]}"
    else:
        brief_summary = f"{summary_parts[0]}: {summary_parts[1]} | {summary_parts[2]}"
    
    # Ensure we stay within the limit
    if len(brief_summary) > max_summary_length:
        brief_summary = brief_summary[:max_summary_length - 3] + "..."
        
    return brief_summary
