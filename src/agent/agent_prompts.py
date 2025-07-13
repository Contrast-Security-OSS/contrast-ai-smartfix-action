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

from src.utils import debug_log

class AgentPrompts:
    def __init__(self, system_prompt, user_prompt):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt

    @staticmethod
    def process_fix_user_prompt(self, fix_user_prompt: str, skip_writing_security_test: bool) -> str:
        """
        Process the fix user prompt by handling SecurityTest removal.
    
        Args:
            fix_user_prompt: The raw fix user prompt from API
            vuln_uuid: The vulnerability UUID for placeholder replacement
        
        Returns:
            Processed fix user prompt
        """
        # Replace {vuln_uuid} placeholder
        processed_prompt = fix_user_prompt
        if skip_writing_security_test:
            start_str = "4. Where feasible,"
            end_str = "   - **CRITICAL: When mocking"
            replacement_text = f"""
4. Where feasible, add or update tests to verify the fix.
    - **Use the 'Original HTTP Request' provided above as a basis for creating realistic mocked input data or request parameters within your test case.** Adapt the request details (method, path, headers, body) as needed for the test framework (e.g., MockMvc in Spring).
"""

            start_index = processed_prompt.find(start_str)
            end_index = processed_prompt.find(end_str)

            if start_index == -1 or end_index == -1:
                debug_log(f"Error: SecurityTest substring not found.")
                return processed_prompt

            processed_prompt = (
                processed_prompt[:start_index] + replacement_text + processed_prompt[end_index:]
            )
        
        return processed_prompt