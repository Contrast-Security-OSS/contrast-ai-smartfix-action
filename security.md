# Reporting Security Issues

Contrast takes security vulnerabilities seriously. We appreciate your efforts to responsibly disclose your findings, and will make every effort to acknowledge your contributions.

To report a security issue, please see our official [Vulnerability Disclosure Policy
](https://www.contrastsecurity.com/disclosure-policy)

Contrast will send a response indicating the next steps in handling your report. After the initial reply to your report, the security team will keep you informed of the progress towards a fix and full announcement, and may ask for additional information or guidance.

Report security bugs in third-party modules to the person or team maintaining the module.

## Security Features

### Command Allowlist Validation

SmartFix includes built-in security controls to prevent arbitrary command execution in GitHub Actions workflows. All build and format commands are validated against a strict allowlist before execution.

**Protected Configuration:**
- `BUILD_COMMAND` - Validated against allowed build tools and test frameworks
- `FORMATTING_COMMAND` - Validated against allowed code formatters

**Security Controls:**
- ✅ Allowlist of approved executables (build tools, test frameworks, formatters)
- ✅ Dangerous pattern detection (command substitution, eval, exec, rm -rf)
- ✅ Shell command restrictions (no inline execution via -c flag)
- ✅ File redirect validation (relative paths only, no traversal attacks)
- ✅ Operator validation (only safe command chaining)

For detailed information about allowed commands and security restrictions, see the [Command Allowlist section in the README](README.md#command-allowlist).

## Learning More About Security

To learn more about securing your applications with Contrast, please see the [our docs](https://docs.contrastsecurity.com/?lang=en).
