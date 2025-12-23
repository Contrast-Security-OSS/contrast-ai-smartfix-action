# SmartFix Review Prompts

This directory contains reusable prompts for evaluating SmartFix's automated security fixes.

## Available Prompts

### smartfix-pr-review.md

**Purpose:** Systematically review open PRs in E2E test repositories to evaluate the quality and effectiveness of SmartFix's cybersecurity fixes.

**When to Use:**
- After SmartFix has created PRs in your E2E test repositories
- To validate that security vulnerabilities are properly fixed
- To assess SmartFix's fix quality across multiple vulnerability types
- Before merging SmartFix PRs into your test baseline

**How to Use:**

1. Navigate to an E2E test repository (Java, Python, .NET, Node.js, etc.)
2. Run Claude Code with the prompt:
   ```bash
   claude "Please follow the review instructions in test/prompts/smartfix-pr-review.md from the contrast-ai-smartfix-action repo"
   ```

   Or if you've copied the prompt locally:
   ```bash
   claude "$(cat path/to/smartfix-pr-review.md)"
   ```

3. Claude will:
   - Discover all open SmartFix PRs
   - Extract vulnerability descriptions from PR bodies
   - Analyze code changes and verify fixes
   - Read surrounding code to confirm findings
   - Generate detailed security assessment reports

**What You'll Get:**
- Per-PR security fix effectiveness scores (0-100)
- Analysis of strengths and weaknesses
- Test coverage assessment
- Specific recommendations for improvements
- Summary statistics across all PRs
- Pattern analysis of SmartFix's fix quality

**Example Output Structure:**
```
PR #123: Fix SQL Injection in User Login
- Fix Status: YES
- Confidence: HIGH
- Score: 95/100
- Strengths: Proper input validation, parameterized queries
- Test Coverage: Comprehensive
- Recommendations: Add edge case for Unicode characters
```

## Contributing New Prompts

When adding new review prompts:
1. Name files descriptively: `<purpose>-review.md`
2. Include clear step-by-step instructions
3. Emphasize verification and avoiding false positives
4. Provide structured output format examples
5. Update this README with usage instructions
