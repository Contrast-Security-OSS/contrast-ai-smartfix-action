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
from typing import Dict, Any, List, Optional
from src.utils import debug_log, log
import src.telemetry_handler as legacy_telemetry_handler

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
        # For Phase 1, use the legacy initialization
        if hasattr(legacy_telemetry_handler, 'initialize_telemetry'):
            legacy_telemetry_handler.initialize_telemetry()
        
        # Create a base telemetry structure
        return {
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
                "enableFullTelemetry": self.enable_full_telemetry,
                "buildCommandRunTestsIncluded": False,
                "formattingCommandProvided": False
            },
            "resultInfo": {
                "prCreated": False,
                "confidence": None,
                "aiSummaryReport": None,
                "filesModified": 0
            },
            "additionalAttributes": {
                "remediationId": None
            },
            "agentEvents": [],
            "logMessages": []
        }
    
    def update_telemetry(self, key_path: str, value: Any) -> None:
        """
        Updates a specific key in the telemetry data using dot notation.
        
        Args:
            key_path: The path to the key in dot notation (e.g., "vulnInfo.vulnId")
            value: The value to set
        """
        # For Phase 1, use the legacy implementation
        legacy_telemetry_handler.update_telemetry(key_path, value)
        
        # Also update our local copy
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
        # For Phase 1, use the legacy implementation
        if hasattr(legacy_telemetry_handler, 'reset_vuln_specific_telemetry'):
            legacy_telemetry_handler.reset_vuln_specific_telemetry()
        
        # Also reset in our local copy
        self.telemetry_data["vulnInfo"] = {
            "vulnId": None,
            "vulnRule": None
        }
        self.telemetry_data["resultInfo"] = {
            "prCreated": False,
            "confidence": None,
            "aiSummaryReport": None,
            "filesModified": 0
        }
        self.telemetry_data["additionalAttributes"]["remediationId"] = None
    
    def add_log_message(self, message: str) -> None:
        """
        Adds a log message to the telemetry data.
        
        Args:
            message: The log message to add
        """
        # For Phase 1, use the legacy implementation if available
        if hasattr(legacy_telemetry_handler, 'add_log_message'):
            legacy_telemetry_handler.add_log_message(message)
        
        # Also add to our local copy
        self.log_messages.append(message)
        
        # Only include logs in telemetry if full telemetry is enabled
        if self.enable_full_telemetry:
            if "logMessages" not in self.telemetry_data:
                self.telemetry_data["logMessages"] = []
            self.telemetry_data["logMessages"].append(message)
    
    def add_agent_event(self, event_data: Dict[str, Any]) -> None:
        """
        Adds an agent event to the telemetry data.
        
        Args:
            event_data: The agent event data
        """
        # For Phase 1, use the legacy implementation if available
        if hasattr(legacy_telemetry_handler, 'add_agent_event'):
            legacy_telemetry_handler.add_agent_event(event_data)
        
        # Also add to our local copy
        if "agentEvents" not in self.telemetry_data:
            self.telemetry_data["agentEvents"] = []
        self.telemetry_data["agentEvents"].append(event_data)
    
    def get_telemetry_data(self) -> Dict[str, Any]:
        """
        Gets the current telemetry data.
        
        Returns:
            dict: The telemetry data
        """
        # For Phase 1, use the legacy implementation
        if hasattr(legacy_telemetry_handler, 'get_telemetry_data'):
            return legacy_telemetry_handler.get_telemetry_data()
        
        # Return our local copy
        return self.telemetry_data
    
    def create_ai_summary_report(self, ai_fix_summary_full: str) -> str:
        """
        Creates a brief summary report from the full AI summary.
        
        Args:
            ai_fix_summary_full: The full AI summary
            
        Returns:
            str: A brief summary (255 chars max)
        """
        # For Phase 1, use the legacy implementation if available
        if hasattr(legacy_telemetry_handler, 'create_ai_summary_report'):
            return legacy_telemetry_handler.create_ai_summary_report(ai_fix_summary_full)
        
        # Fallback implementation
        max_length = 255
        
        # Extract content from <pr_body> tags if present
        pr_body_match = re.search(r"<pr_body>(.*?)</pr_body>", ai_fix_summary_full, re.DOTALL)
        summary = pr_body_match.group(1) if pr_body_match else ai_fix_summary_full
        
        # Find the first heading that might contain "Summary" or "Overview"
        summary_section = None
        for heading_match in re.finditer(r"^#+\s*(.*Summary|.*Overview|.*Changes).*$", summary, re.MULTILINE | re.IGNORECASE):
            summary_section = heading_match.group(0)
            break
        
        if summary_section:
            # Get the text after the heading until the next heading
            next_heading_match = re.search(rf"{re.escape(summary_section)}(.*?)^#+\s", summary, re.DOTALL | re.MULTILINE)
            if next_heading_match:
                summary = next_heading_match.group(1).strip()
            else:
                # Get all text after the heading
                heading_index = summary.find(summary_section)
                if heading_index >= 0:
                    summary = summary[heading_index + len(summary_section):].strip()
        
        # Clean up the summary - remove markdown formatting, etc.
        summary = re.sub(r'[\*_#`]', '', summary)  # Remove common markdown formatting
        summary = re.sub(r'\s+', ' ', summary)     # Normalize whitespace
        
        # Truncate to max length
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        
        return summary
    
    def send_telemetry_data(self) -> bool:
        """
        Sends the collected telemetry data.
        
        Returns:
            bool: True if sending was successful, False otherwise
        """
        # For Phase 1, use the legacy implementation
        from src.contrast_api import send_telemetry_data
        return send_telemetry_data()