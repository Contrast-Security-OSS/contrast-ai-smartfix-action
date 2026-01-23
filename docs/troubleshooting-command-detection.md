# Troubleshooting Command Detection

This guide helps you diagnose and fix issues when SmartFix cannot auto-detect your build or format commands.

## What SmartFix Does When Detection Fails

SmartFix uses a **three-phase detection approach** with graceful degradation:

### Phase 1: Deterministic Detection (Tries Real Builds)

**Process:**
1. Scans for marker files (`pom.xml`, `package.json`, etc.)
2. Generates candidate commands based on markers
3. Validates against security allowlist
4. **Runs actual build command** to verify it works in your project
5. Returns first command that successfully executes

**On Failure:**

| Scenario | BUILD_COMMAND Required? | Behavior |
|----------|------------------------|----------|
| No marker files found | Yes | **PHASE 2 FALLBACK** - Triggers LLM-based detection with failure context |
| No marker files found | No | **SKIP DETECTION** - Logs message, proceeds without build command |
| Tool not installed | Yes | **PHASE 2 FALLBACK** - Triggers LLM-based detection with tool availability errors |
| Tool not installed | No | **SKIP DETECTION** - Logs message, proceeds |
| Build command fails | Yes | **PHASE 2 FALLBACK** - Triggers LLM-based detection with build error output |
| FORMATTING_COMMAND detection fails | N/A (never required) | **SKIP** - Logs info message, formatting is optional |

**Log Messages:**
```
# Success
Phase 1: Auto-detected BUILD_COMMAND: mvn test

# Failure (triggers Phase 2)
Phase 1: Could not detect BUILD_COMMAND from deterministic detection
Attempting Phase 2 LLM-based detection...

# Failure (format command - optional)
Could not auto-detect FORMATTING_COMMAND (optional)
```

### Phase 2: LLM-Based Detection (Iterative)

**Process:**
1. Receives Phase 1 failure history as context
2. LLM analyzes project structure and previous failures
3. Suggests a command
4. Validates command against security allowlist
5. Tests command execution
6. If fails: extracts errors, adds to history, repeats (up to 6 attempts by default)
7. Returns first successful command or None if all attempts exhausted

**On Failure:**

| Scenario | Behavior |
|----------|----------|
| Security validation fails | **CONTINUE TO NEXT ITERATION** - Adds validation error to history, tries again |
| Command execution fails | **CONTINUE TO NEXT ITERATION** - Extracts build errors, adds to history, tries again |
| Max attempts exhausted (default 6) | **PHASE 3 FALLBACK** - Returns None, triggers no-op fallback command |

**Log Message on Max Attempts:**
```
Phase 2 LLM detection exhausted 6 attempts without finding valid build command | Build files found: pom.xml, build.gradle | Tried 6 command(s) | Last attempt: mvn -P integration-tests test | Last error: [INFO] Tests run: 3, Failures: 2...
Falling back to no-op build command
```

**Configuration:**
- Set `MAX_COMMAND_DETECTION_ATTEMPTS` env var to adjust iteration limit (default: 6, max: 10)

### Phase 3: No-Op Fallback (Graceful Degradation)

**When Triggered:**
- Both Phase 1 and Phase 2 fail to find a working build command
- BUILD_COMMAND is required for the current task

**What Happens:**
1. SmartFix uses a no-op fallback command (`echo "No build command available"`)
2. **Remediation continues** instead of failing
3. Fix agent can still generate code changes
4. Changes are untested (no build verification)
5. QA agent skips build validation

**Behavior:**
- ✅ **PR is created** with generated fix
- ⚠️ **No test verification** - fixes are unvalidated
- ⚠️ **Warning added to PR description** - indicates untested changes
- ✅ **Human review required** - reviewers must validate manually

**Log Messages:**
```
Phase 1 and Phase 2 detection both failed
Using no-op fallback: echo "No build command available"
⚠️  WARNING: Changes will not be tested automatically
```

**Why No-Op Instead of Failure:**
- Allows SmartFix to generate fixes even when build detection fails
- Better UX: generates PR with warning vs failing completely
- Gives humans the option to review untested fixes
- Prevents build detection issues from blocking all remediation

**When This Might Happen:**
- Unsupported build system (Bazel, custom tools)
- Non-standard project structure
- Build requires manual setup SmartFix cannot detect
- Tests don't exist or are not runnable in CI

**Best Practice:**
If you see this warning frequently, set BUILD_COMMAND explicitly:
```yaml
env:
  BUILD_COMMAND: "your-test-command"
```

### When Is BUILD_COMMAND Required?

BUILD_COMMAND is **required** only when:
- `RUN_TASK=generate_fix` (default)
- AND `CODING_AGENT=SMARTFIX` (default)

For other tasks or agents, BUILD_COMMAND is optional.

## Common Issues

### 1. No Build System Marker Files Found

**Problem:** SmartFix cannot find marker files like `pom.xml`, `package.json`, `build.gradle`, etc.

**What Happens:**
- Phase 1 deterministic detection returns no candidates
- **Phase 2 LLM detection** is triggered with "no marker files" context
- If Phase 2 also fails: **Phase 3 no-op fallback** is used
- Remediation continues with untested changes
- Logs: `Phase 1: Could not detect BUILD_COMMAND from deterministic detection` → `Attempting Phase 2 LLM-based detection...`

**Solution:**
```yaml
# Manually specify your build command in GitHub Actions workflow
env:
  BUILD_COMMAND: "your-build-command"
```

**Example:**
```yaml
env:
  BUILD_COMMAND: "bazel test //..."  # For Bazel projects
  BUILD_COMMAND: "cargo test"       # For Rust projects
  BUILD_COMMAND: "go test ./..."    # For Go projects
```

### 2. Build Tool Not Installed

**Problem:** Marker file exists but the build tool isn't available in the GitHub Actions environment.

**What Happens:**
- Phase 1 deterministic detection finds marker files and generates candidates
- Tests each candidate with `--version` flag and actual build execution
- All candidates fail (tool not installed or build fails)
- **Phase 2 LLM detection** is triggered with tool availability errors
- If Phase 2 also fails: **Phase 3 no-op fallback** is used
- Logs: `Phase 1: Could not detect BUILD_COMMAND from deterministic detection` → `Attempting Phase 2 LLM-based detection...`

**Solution:**

Install the required build tool before running SmartFix:

```yaml
steps:
  # Install build tool first
  - name: Set up Node.js
    uses: actions/setup-node@v4
    with:
      node-version: '20'

  # Then run SmartFix (will auto-detect npm commands)
  - name: Run SmartFix
    uses: contrast-security-oss/contrast-ai-smartfix-action@main
```

### 3. Custom Build Command Needed

**Problem:** Auto-detection finds a command, but you need a different one.

**What Happens:**
- Phase 1 deterministic detection succeeds and returns a valid command (e.g., `mvn test`)
- SmartFix uses the detected command
- Command may not match your project's specific needs (e.g., missing profile flags)

**Solution:**

Override with your custom command:

```yaml
env:
  BUILD_COMMAND: "mvn clean verify -P integration-tests"
```

SmartFix will use your command instead of auto-detecting.

### 4. Monorepo with Non-Standard Structure

**Problem:** Monorepo has build files in unusual locations.

**Solution:**

SmartFix auto-detects monorepo structures, but if detection fails:

```yaml
env:
  BUILD_COMMAND: "mvn -f services/backend/pom.xml test"
```

Or use workspace-level commands:

```yaml
env:
  BUILD_COMMAND: "nx test backend"  # For Nx monorepos
  BUILD_COMMAND: "turbo run test"   # For Turborepo
```

### 5. Detection Succeeds But Command Fails During Fix Generation

**Problem:** SmartFix detects a command but it fails when executed during fix generation.

**What Happens:**
- Phase 1 deterministic detection succeeds and returns a valid command
- During fix generation, SmartFix runs the command
- Command fails due to environment issues (not command detection issues)
- Fix generation may fail if tests cannot run

**Causes:**
- Missing dependencies (not installed via workflow setup steps)
- Environment variables not set
- Database/service not available
- Wrong working directory
- Tests require specific setup not present in CI

**Solution:**

Set up your environment before SmartFix runs:

```yaml
steps:
  - uses: actions/checkout@v4

  # Install dependencies
  - name: Set up JDK
    uses: actions/setup-java@v4
    with:
      java-version: '17'

  - name: Cache Maven packages
    uses: actions/cache@v4
    with:
      path: ~/.m2
      key: ${{ runner.os }}-m2-${{ hashFiles('**/pom.xml') }}

  # Set environment variables
  - name: Set up environment
    run: |
      echo "DATABASE_URL=postgres://test:test@localhost:5432/test" >> $GITHUB_ENV

  # Now run SmartFix
  - uses: contrast-security-oss/contrast-ai-smartfix-action@main
```

### 6. Format Command Not Needed

**Problem:** SmartFix tries to auto-detect a format command but you don't want one.

**What Happens:**
- SmartFix attempts to detect FORMATTING_COMMAND (optional, never required)
- If detection succeeds: formatting is applied during fix generation
- If detection fails: **Action continues normally** - formatting is skipped
- Logs: `Could not auto-detect FORMATTING_COMMAND (optional)`

**Solution:**

Explicitly disable formatting if you don't want SmartFix to attempt detection:

```yaml
env:
  FORMATTING_COMMAND: ""  # Skip formatting entirely
```

Or let SmartFix handle it automatically (format commands are optional and won't cause failures).

### 7. Multiple Build Systems in One Repo

**Problem:** Repository has multiple marker files (e.g., both `pom.xml` and `package.json`).

**What Happens:**
- Phase 1 deterministic detection generates candidates from **all** detected build systems
- Tests candidates in priority order (Maven → Gradle → Python → Node.js → PHP → .NET → Make)
- Uses the **first command that successfully executes** (not just passes --version)
- May not choose the build system you expect

**Solution (if wrong one is chosen):**

Explicitly set the command you want:

```yaml
env:
  BUILD_COMMAND: "npm test"  # Prefer npm over Maven
```

### 8. Security Validation Failure

**Problem:** Command fails security validation.

**What Happens:**

**For Deterministic Detection:**
- Generated candidates are pre-validated and should always pass
- If a candidate somehow fails validation: **skipped, continues to next candidate**
- This is a bug if it occurs with auto-detected commands

**For Phase 2 LLM Detection:**
- LLM suggests a command
- Validation fails (e.g., dangerous pattern, disallowed executable)
- **Continues to next iteration** with validation error in prompt
- LLM tries again with different command
- After 6 attempts: **Phase 3 no-op fallback** is used

**For Manual Commands (action.yml):**
- Commands from `action.yml` inputs are **trusted and skip validation**
- Can use any command regardless of allowlist

**For Manual Commands (env var set programmatically):**
- Validated against allowlist
- If fails: **Action fails with `ConfigurationError`**

**Error Message Example:**
```
Command validation failed: Command contains dangerous pattern: $(
Command: mvn test && $(cat secrets.txt)
Security validation failed. Please remove unsafe shell operations.
```

**Solution:**

If this happens with auto-detected commands (this is a bug):

1. **Check if command was manually set with unsafe patterns:**
   ```yaml
   # ❌ Unsafe - will be rejected
   BUILD_COMMAND: "mvn test && rm -rf /"

   # ✅ Safe - will pass validation
   BUILD_COMMAND: "mvn test"
   ```

2. **Report the issue** if auto-detection generated an invalid command (this is a bug).

### 9. BUILD_COMMAND Not Required (Task Skips Detection)

**Problem:** User expects detection to run but it's being skipped.

**What Happens:**
- Detection is **skipped entirely** when BUILD_COMMAND is not required
- BUILD_COMMAND is only required when:
  - `RUN_TASK=generate_fix` (default)
  - AND `CODING_AGENT=SMARTFIX` (default)
- For other tasks (`RUN_TASK=merge`, `RUN_TASK=closed`): detection is skipped
- For other agents (`CODING_AGENT=COPILOT`, `CLAUDE_CODE`): detection may be skipped

**Log Message:**
```
BUILD_COMMAND not required for current task/agent, skipping detection
```

**Solution:**

This is expected behavior. Detection only runs when BUILD_COMMAND is required. If you want to test detection:
- Ensure `RUN_TASK=generate_fix` (default)
- Ensure `CODING_AGENT=SMARTFIX` (default)

### 10. Both Phase 1 and Phase 2 Fail (No-Op Fallback)

**Problem:** Neither deterministic nor LLM-based detection can find a working build command.

**What Happens:**
1. **Phase 1 fails:** No marker files found, or all candidates fail, or builds don't pass
2. **Phase 2 triggered:** LLM attempts to detect command based on project structure
3. **Phase 2 exhausts all attempts:** After 6 iterations, still no working command
4. **Phase 3 no-op fallback:** SmartFix uses `echo "No build command available"`
5. **Remediation continues:** Fix is generated but **not tested**
6. **PR created with warning:** Indicates changes are untested and require manual review

**Log Messages:**
```
Phase 1: Could not detect BUILD_COMMAND from deterministic detection
Attempting Phase 2 LLM-based detection...
Phase 2 LLM detection exhausted 6 attempts without finding valid build command | Build files found: ... | Last attempt: ... | Last error: ...
Falling back to no-op build command
⚠️  WARNING: Changes will not be tested automatically
Using BUILD_COMMAND: echo "No build command available"
```

**Why This Happens:**
- **Unsupported build system:** Bazel, Buck, custom build tools not in allowlist
- **Non-standard structure:** Tests in unusual locations, custom scripts
- **Complex setup:** Build requires services, databases, or manual configuration
- **No tests:** Project has no runnable test suite
- **Permissions issues:** CI environment lacks access to required resources

**What Gets Created:**
- ✅ PR with proposed security fix
- ⚠️ Warning in PR description: "Changes not validated by automated tests"
- ⚠️ Recommendation for human review and manual testing
- ✅ Code changes that may fix the vulnerability (untested)

**Solution:**

**Option 1: Set BUILD_COMMAND explicitly (recommended)**
```yaml
env:
  BUILD_COMMAND: "your-test-command"
```

**Option 2: Accept untested fixes**
- Review PR manually
- Test changes in your local environment
- Merge if fix looks correct

**Option 3: Report unsupported build system**
- Open an issue requesting support for your build tool
- Include marker files, build commands, and project structure

**Best Practice:**
If you see Phase 3 fallback frequently, always set BUILD_COMMAND explicitly to ensure your fixes are tested.

## Debugging

### Enable Debug Mode

See detailed detection and configuration logs:

```yaml
env:
  DEBUG_MODE: "true"
```

**What DEBUG_MODE Shows:**
- Configuration values at startup
- Which marker files were found
- Which commands were generated during deterministic detection
- Which command was selected (if any)
- Full error messages and stack traces
- LLM detection iteration details (if applicable)

**Debug mode does NOT show:**
- Why individual commands were rejected during deterministic detection (this is not logged)
- Command availability test results (--version checks)

**Tip:** Most useful for understanding why detection failed or which command was chosen.

### Check Logs

**Success Messages:**
```
Phase 1: Auto-detected BUILD_COMMAND: mvn test
Auto-detected FORMATTING_COMMAND: prettier --write .
```

**Phase 1 Failure (triggers Phase 2):**
```
Phase 1: Could not detect BUILD_COMMAND from deterministic detection
Attempting Phase 2 LLM-based detection...
```

**Phase 2 Success:**
```
Phase 2: Successfully detected BUILD_COMMAND: mvn -P integration-tests test
```

**Phase 2 Failure (triggers Phase 3):**
```
Phase 2 LLM detection exhausted 6 attempts without finding valid build command | Build files found: pom.xml | Tried 6 command(s) | Last attempt: mvn -P ci test | Last error: [build output...]
Falling back to no-op build command
⚠️  WARNING: Changes will not be tested automatically
Using BUILD_COMMAND: echo "No build command available"
```

**Format Command (optional):**
```
Could not auto-detect FORMATTING_COMMAND (optional)
```

See **"What SmartFix Does When Detection Fails"** section above for complete three-phase behavior details.

### Verify Marker Files Exist

Check that your project has the expected marker files:

```bash
# In your repository
ls -la pom.xml package.json build.gradle pytest.ini
```

### Test Command Locally

Before relying on auto-detection, verify your command works:

```bash
# Test the command SmartFix would use
mvn test
npm test
pytest
```

## Best Practices

### 1. Use Standard Project Structure

SmartFix works best with standard project layouts:

```
✅ Good (standard)
my-project/
  pom.xml
  src/
    main/
    test/

❌ Challenging (non-standard)
my-project/
  config/
    maven/
      pom.xml
  sources/
```

### 2. Include Lock Files

For Node.js projects, commit lock files for accurate package manager detection:

- `package-lock.json` (npm)
- `yarn.lock` (yarn)
- `pnpm-lock.yaml` (pnpm)
- `bun.lockb` (bun)

### 3. Test in CI First

Before relying on auto-detection in production:

1. Create a test PR
2. Let SmartFix auto-detect
3. Verify the detected command works
4. Adjust if needed

### 4. Document Custom Commands

If you must use custom commands, document why in your workflow:

```yaml
env:
  # Custom command needed because:
  # - We use a wrapper script for test setup
  # - Standard 'mvn test' doesn't include integration tests
  BUILD_COMMAND: "./scripts/run-all-tests.sh"
```

## Getting Help

If auto-detection isn't working:

1. **Check this guide** for your specific issue
2. **Enable DEBUG_MODE** and review logs
3. **Check [Supported Build Systems](./supported-build-systems.md)** to verify your tool is supported
4. **Set BUILD_COMMAND manually** as a workaround
5. **Open an issue** with:
   - Your build system and version
   - Relevant marker files in your repo
   - Debug logs
   - Expected vs actual behavior

## Related Documentation

- [Supported Build Systems](./supported-build-systems.md) - Complete list of supported build systems
- [Command Validation](./command-validation.md) - Security validation rules
- [Configuration](../README.md#configuration) - All environment variables
