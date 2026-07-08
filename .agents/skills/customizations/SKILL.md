---
name: customizations
description: Explains how and when to use agent customizations, skills, rules, and instruction files.
---

# Agent Customizations Guidelines

Agents can be customized to adapt to project-specific or global workflows. Here is a breakdown of how and when to use different customization files:

## 1. Skills (`skills/<skill_name>/SKILL.md`)
**What they are**: Folders of instructions, scripts, and resources that extend an agent's capabilities for specialized, conditional tasks.
**When to use**: Use Skills when you need to teach the agent how to handle a complex, specific task, framework, component, or tool that it doesn't do natively out-of-the-box (e.g., configuring `ibeam`, debugging `truecharts`, using a proprietary CLI). 
**How to use**: 
- Create a directory `skills/<skill_name>/` (relative to the customization root `.agents/`).
- Inside, create a `SKILL.md` file containing YAML frontmatter (`name`, `description`) and markdown instructions. 
- The description is trigger-matched, meaning the agent will only load and read the instructions when the current task seems relevant to the skill's description. 
- Keep instructions under 500 lines. Use a `references/` subdirectory for longer documentation.

## 2. Rules and General Instructions (`AGENTS.md`)
**What they are**: A markdown file containing style guidelines, behavioral constraints, and universal repository rules.
**When to use**: Use this for rules that the agent MUST ALWAYS FOLLOW WITHOUT EXCEPTION across all tasks in the repository. (e.g., "Always use static mount paths", "Never commit unencrypted secrets").
**How to use**:
- Append rules to `.agents/AGENTS.md` (Project-Scoped) or the global config root (Global). This file is automatically injected into the agent's context for every interaction in the workspace. Avoid putting highly specific, conditional knowledge here to preserve context window space; use Skills for conditional knowledge instead.

## 3. Knowledge Items (KI) (`<appDataDir>/knowledge/artifacts/`)
**What they are**: Curated, localized context about past work in the repository (e.g., architectural decisions, established patterns, debugging resolutions).
**When to use**: Use KIs to record snapshots of past work to prevent the agent from repeating the same research or making the same mistakes. Examples include "Add logging pattern", "Known issues with X component".
**How to use**:
- Summaries of KIs are automatically presented to the agent at the start of a conversation. The agent checks these summaries and reads the related KI artifacts if relevant before doing independent research.
