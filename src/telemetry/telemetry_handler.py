#-
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

import json
import datetime
import platform
import os
import re
import copy
from typing import Dict, Any, List, Optional
import sys
import os
# Add project root to Python path to ensure imports work correctly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    
from src.utils import debug_log, log
# Legacy telemetry module is no longer used
# import src.telemetry_handler as legacy_telemetry_handler
from src.config_compat import VERSION, CONTRAST_HOST, BUILD_COMMAND, FORMATTING_COMMAND, AGENT_MODEL, ENABLE_FULL_TELEMETRY

from src.utils import singleton

@singleton
class TelemetryHandler:
    """
    Manages the collection and sending of telemetry data.
    """
    
    def __init__(self, contrast_api_client=None, enable_full_telemetry=True):
        """
        Initialize the telemetry handler.
        
        Args:
            contrast_api_client: Optional API client for sending telemetry
            enable_full_telemetry: Whether to include sensitive data in telemetry
        """
        self.contrast_api_client = contrast_api_client
        self.enable_full_telemetry = enable_full_telemetry
        self.telemetry_data = self._initialize_telemetry()
        self.log_messages = []
    
    def _initialize_telemetry(self) -> Dict[str, Any]:
        """
        Initialize the telemetry data structure.
        
        Returns:
            dict: The initialized telemetry data structure
        """
        # No longer initializing legacy telemetry
        
        # Create a comprehensive telemetry structure
        telemetry_data = {
            "teamServerHost": CONTRAST_HOST,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "platform": platform.system(),
            "platformVersion": platform.release(),
            "python": platform.python_version(),
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
                "sanitizedBuildCommand": BUILD_COMMAND,
                "buildCommandRunTestsIncluded": False,
                "sanitizedFormatCommand": FORMATTING_COMMAND,
                "aiProvider": None,
                "aiModel": None,
                "enableFullTelemetry": self.enable_full_telemetry
            },
            "resultInfo": {
                "prCreated": False,
                "confidence": None,
                "aiSummaryReport": None,
                "filesModified": 0
            },
            "agentEvents": [],
            "additionalAttributes": {
                "fullLog": "",
                "scriptVersion": VERSION,
                "remediationId": None,
                "prStatus": None
            }
        }
        
        # Parse agent model to get provider and model information
        agent_model = AGENT_MODEL
        if agent_model:
            parts = agent_model.split('/', 1)
            telemetry_data["configInfo"]["aiProvider"] = parts[0]
            if len(parts) > 1:
                telemetry_data["configInfo"]["aiModel"] = parts[1]
            else:
                telemetry_data["configInfo"]["aiModel"] = parts[0]
        
        return telemetry_data
    
    def update_telemetry(self, key_path: str, value: Any) -> None:
        """
        Updates a specific key in the telemetry data using dot notation.
        
        Args:
            key_path: The path to the key in dot notation (e.g., "vulnInfo.vulnId")
            value: The value to set
        """
        # No longer updating legacy telemetry
        
        # Update our local copy
        parts = key_path.split('.')
        current = self.telemetry_data
        
        # Navigate to the nested dictionary
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Set the value
        current[parts[-1]] = value
    
    def reset_vuln_specific_telemetry(self) -> None:
        """Resets vulnerability-specific telemetry data."""
        # No longer resetting legacy telemetry
        
        # Reset in our local copy
        self.telemetry_data["vulnInfo"] = {
            "vulnId": None,
            "vulnRule": None
        }
        self.telemetry_data["appInfo"] = {
            "programmingLanguage": None,
            "technicalStackInfo": None,
            "frameworksAndLibraries": []
        }
        self.telemetry_data["resultInfo"] = {
            "prCreated": False,
            "confidence": None,
            "aiSummaryReport": None,
            "filesModified": 0
        }
        self.telemetry_data["additionalAttributes"]["remediationId"] = None
        self.telemetry_data["agentEvents"] = []
    
    def add_log_message(self, message: str) -> None:
        """
        Adds a log message to the telemetry data.
        
        Args:
            message: The log message to add
        """
        # No longer adding logs to legacy telemetry
        
        # Add to our local log messages list
        self.log_messages.append(message)
        
        # Only include logs in telemetry if full telemetry is enabled
        if self.enable_full_telemetry:
            # Ensure additionalAttributes exists
            if "additionalAttributes" not in self.telemetry_data:
                self.telemetry_data["additionalAttributes"] = {}
            
            # Append to fullLog with a newline separator
            current_log = self.telemetry_data["additionalAttributes"].get("fullLog")
            if current_log:
                self.telemetry_data["additionalAttributes"]["fullLog"] = current_log + "\n" + message
            else:
                self.telemetry_data["additionalAttributes"]["fullLog"] = message
    
    def add_agent_event(self, event_data: Dict[str, Any]) -> None:
        """
        Adds an agent event to the telemetry data.
        
        Args:
            event_data: The agent event data
        """
        # No longer adding agent events to legacy telemetry
        
        # Add to our local copy
        if "agentEvents" not in self.telemetry_data:
            self.telemetry_data["agentEvents"] = []
        self.telemetry_data["agentEvents"].append(event_data)
    
    def get_telemetry_data(self) -> Dict[str, Any]:
        """
        Gets the current telemetry data.
        
        Returns:
            dict: The telemetry data, processed to ensure JSON serializability and
                 proper truncation of large fields based on ENABLE_FULL_TELEMETRY setting
        """
        # Make a deep copy to ensure we're not modifying the original
        telemetry_copy = copy.deepcopy(self.telemetry_data)
        
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
        if not self.enable_full_telemetry:
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
        
        # Adjust debug message based on whether fullLog is being sent
        if self.enable_full_telemetry:
            debug_log(f"Telemetry payload size: {json_size_kb:.2f}KB (fullLog is being sent in its entirety)")
        else:
            debug_log(f"Telemetry payload size: {json_size_kb:.2f}KB (fullLog is excluded per ENABLE_FULL_TELEMETRY=false setting)")
        
        # No longer getting data from legacy telemetry
        
        return telemetry_copy
    
    def create_ai_summary_report(self, ai_fix_summary_full: str) -> str:
        """
        Creates a brief summary report from the full AI summary.
        
        Args:
            ai_fix_summary_full: The full AI summary
            
        Returns:
            str: A brief summary (255 chars max)
        """
        # Ensure we have content to work with
        if not ai_fix_summary_full:
            return "AI fix applied"
        
        # Extract content from <pr_body> tags if present
        pr_body_match = re.search(r"<pr_body>(.*?)</pr_body>", ai_fix_summary_full, re.DOTALL)
        pr_body = pr_body_match.group(1) if pr_body_match else ai_fix_summary_full
        
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
        
        # No longer creating summary from legacy telemetry
            
        return brief_summary
    
    def send_telemetry_data(self) -> bool:
        """
        Sends the collected telemetry data.
        
        Returns:
            bool: True if sending was successful, False otherwise
        """
        # Make sure we have a contrast_api_client
        if not self.contrast_api_client:
            debug_log("No contrast_api_client provided to TelemetryHandler. Cannot send telemetry data.")
            # No longer using legacy telemetry for sending data
            return False
            
        # Use the contrast_api_client to send the data
        try:
            # ContrastApiClient.send_telemetry_data() retrieves telemetry data internally
            # from the legacy telemetry_handler, so we don't need to get it here
            result = self.contrast_api_client.send_telemetry_data()
            return result
        except Exception as e:
            log(f"Error sending telemetry data: {e}", is_error=True)
            return False