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
    """Returns a copy of the current telemetry data object that is JSON serializable."""
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
            
    # Helper function to truncate large text fields within agent events
    def truncate_large_text_fields(obj, max_length=5000):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and len(value) > max_length:
                    # Truncate the string and add an indicator
                    obj[key] = value[:int(max_length/2)] + f"...[{len(value) - max_length} characters truncated]..." + value[-int(max_length/2):]
                elif isinstance(value, (dict, list)):
                    truncate_large_text_fields(value, max_length)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, (dict, list)):
                    truncate_large_text_fields(item, max_length)
        return obj
    
    # Make the entire telemetry data structure JSON serializable
    telemetry_copy = ensure_json_serializable(telemetry_copy)
    
    # Truncate fullLog to a reasonable size to avoid database issues
    # Most database JSON columns have limits of ~64KB or less
    if "additionalAttributes" in telemetry_copy and "fullLog" in telemetry_copy["additionalAttributes"]:
        full_log = telemetry_copy["additionalAttributes"]["fullLog"]
        if len(full_log) > 20000:  # Limit to 20KB which is safe for most DB columns
            # Keep only the end (most recent logs)
            telemetry_copy["additionalAttributes"]["fullLog"] = f"...[First {len(full_log) - 20000} characters truncated]...\n{full_log[-20000:]}"
    
    # Also truncate any large text fields in agent events
    if "agentEvents" in telemetry_copy:
        truncate_large_text_fields(telemetry_copy["agentEvents"])
    
    # Also truncate aiSummaryReport if it's too large
    if "resultInfo" in telemetry_copy and "aiSummaryReport" in telemetry_copy["resultInfo"] and telemetry_copy["resultInfo"]["aiSummaryReport"]:
        summary = telemetry_copy["resultInfo"]["aiSummaryReport"]
        if len(summary) > 10000:  # 10KB limit for summary
            telemetry_copy["resultInfo"]["aiSummaryReport"] = f"{summary[:5000]}...[truncated]...{summary[-5000:]}"
    
    if not config.ENABLE_FULL_TELEMETRY:
        # Remove sensitive fields if telemetry is limited
        if "additionalAttributes" in telemetry_copy:
            telemetry_copy["additionalAttributes"] = telemetry_copy["additionalAttributes"].copy()
            telemetry_copy["additionalAttributes"].pop("fullLog", None)
        if "configInfo" in telemetry_copy:
            telemetry_copy["configInfo"] = telemetry_copy["configInfo"].copy()
            telemetry_copy["configInfo"]["sanitizedBuildCommand"] = ""
            telemetry_copy["configInfo"]["sanitizedFormatCommand"] = ""

    # Debug: Print the JSON structure with truncated fullLog
    import json
    debug_copy = copy.deepcopy(telemetry_copy)
    if "additionalAttributes" in debug_copy and "fullLog" in debug_copy["additionalAttributes"]:
        full_log = debug_copy["additionalAttributes"]["fullLog"]
        debug_copy["additionalAttributes"]["fullLog"] = f"... [truncated, showing last 100 chars: {full_log[-100:]}]"
    print("DEBUG - Telemetry structure (with truncated fullLog):")
    print(json.dumps(debug_copy, indent=2, default=str))

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
