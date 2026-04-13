# Reporting Security Issues

Contrast takes security vulnerabilities seriously. We appreciate your efforts to responsibly disclose your findings, and will make every effort to acknowledge your contributions.

To report a security issue, please see our official [Vulnerability Disclosure Policy
](https://www.contrastsecurity.com/disclosure-policy)

Contrast will send a response indicating the next steps in handling your report. After the initial reply to your report, the security team will keep you informed of the progress towards a fix and full announcement, and may ask for additional information or guidance.

Report security bugs in third-party modules to the person or team maintaining the module.

## Learning More About Security

To learn more about securing your applications with Contrast, please see the [our docs](https://docs.contrastsecurity.com/?lang=en).

## "BREAK GLASS" In case of emergency

_Compromised library:_

In the event that a library that SmartFix uses is found to be compromised (like the LiteLLM hack):
- Update requirements.txt, or the appropriate file, to list an uncompromised version of the library
- Regenerate the requirements.lock file with `uv` and inspect to ensure it doesn't include a compromised version
- Verify that the SmartFix workflow functions properly against one of our test applciations to fix a Contrast vulnerability
- Release the updated version of SmartFix by following these instructions: https://contrast.atlassian.net/wiki/spaces/ARCH/pages/4215046180/SmartFix+Action+Releasing+notes