---
name: technical-writing-generic
description: Generic writing skill for operational runbooks, troubleshooting guides, and copy-paste-safe command documentation.
---

# Technical Writing Skill (Generic)

## When To Use This Skill
- Creating runbooks, skills, SOPs, or troubleshooting docs.
- Updating command snippets used by operators.
- Converting ad-hoc fixes into reusable procedures.

## Writing Goals
- Fast to scan under incident pressure.
- Copy/paste runnable commands.
- Clear decision points and validation outcomes.

## Recommended Structure
1. Purpose and scope.
2. When to use.
3. Required inputs/variables.
4. Fast triage workflow.
5. Diagnostics (read-only first).
6. Remediation (smallest safe change first).
7. Validation checklist.
8. Common mistakes and escalation path.

## Command Quality Rules
- Prefer parameterized commands with explicit variables.
- Ensure JSONPath snippets are valid and complete.
- Show expected output shape where useful.
- Separate destructive from read-only commands.

## Style Rules
- Use short headers and imperative steps.
- Keep lists single-level and action-oriented.
- Avoid environment-specific assumptions unless explicitly scoped.
- State preconditions and rollback notes for risky steps.

## Reusability Rules
- Use placeholders like `<namespace>`, `<name>`, `<ip>`.
- Avoid hardcoded hostnames, paths, and cluster names unless required.
- Include both symptom-based and state-based entry points.

## Validation Checklist
- A new operator can run the steps without prior context.
- Commands execute without syntax fixes.
- Outcomes and success criteria are explicit.
- Failure branches include next action, not just diagnostics.
