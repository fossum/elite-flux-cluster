---
name: generate-commit
description: Generates conventional Git commit messages for staged changes in this repository following FluxCD and Kubernetes GitOps standards.
---

# Generate Conventional Commit Message

When asked to generate a commit message or review staged changes, follow these instructions to inspect the Git diff and produce a conventional commit message.

## Instructions

1. **Inspect Staged Changes**: Run `git diff --staged` (or `git diff --cached`) to inspect all currently staged changes.
2. **Determine Conventional Type & Scope**:
   - **Type**: Select from `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`.
   - **Scope**: Use the directory or namespace of the changed application/resource (e.g., `finance`, `media`, `infrastructure`, `sources`).
3. **Format**:
   - **Title Line**: `<type>(<scope>): <short summary>` (imperative, present tense, <= 72 chars).
   - **Body**: Bulleted list highlighting specific manifest/resource additions or modifications:
     - Flux resources (`GitRepository`, `HelmRelease`, `Kustomization`, etc.).
     - Container, podSpec, or ingress configuration updates.
     - Removed or cleaned up obsolete blocks.
