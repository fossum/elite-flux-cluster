---
name: sop-authoring-generic
description: Generic SOP authoring framework for repeatable operational procedures with prerequisites, execution steps, validation, and rollback guidance.
---

# SOP Authoring Skill (Generic)

## When To Use This Skill
- You need a repeatable operational procedure.
- A one-off incident fix should become a standard runbook.
- Teams need consistent execution and handoff quality.

## SOP Blueprint
1. Objective: what this SOP accomplishes.
2. Scope: where it applies and where it does not.
3. Preconditions: required permissions, tools, and system state.
4. Safety constraints: risks, protected resources, and stop conditions.
5. Procedure: ordered actions with expected checkpoints.
6. Validation: objective success criteria.
7. Rollback: steps to restore previous state if validation fails.
8. Escalation: who to contact and what evidence to provide.

## Procedure Writing Rules
- Use explicit verbs and one action per step.
- Place read-only checks before mutation steps.
- Include exact command examples with placeholders.
- State expected output for critical checks.
- Add decision branches for common failure states.

## Operational Quality Gates
- Can a new operator run this without tribal knowledge?
- Are all required inputs listed up front?
- Is rollback possible at each risk point?
- Are monitoring and confirmation steps explicit?

## Example Variable Block
```bash
ENV=<environment>
NS=<namespace>
RESOURCE=<resource-name>
CHANGE_ID=<ticket-or-commit>
```

## Validation Checklist
- Procedure is deterministic and unambiguous.
- Risky steps include guardrails and stop criteria.
- Success and failure outcomes are measurable.
- Post-change verification is included and actionable.
