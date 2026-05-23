---
name: development-workspace
description: Development workspace chart and app guide for the elite-flux-cluster. Use this when asked to modify the generic development workspace chart, multi-repo setup, Tailscale sidecar, PVC behavior, or the Flux app in the development namespace.
---

# Development Workspace Skill — elite-flux-cluster

## Deployment Overview
- **Namespace**: `development`
- **Flux app path**: `apps/development/development-workspace`
- **Flux Kustomization**: `apps/development/development-workspace/ks.yaml`
- **App manifests**: `apps/development/development-workspace/app`
- **HelmRelease**: `apps/development/development-workspace/app/helm-release.yaml`
- **Local chart**: `charts/development-workspace`
- **Chart values**: `charts/development-workspace/values.yaml`
- **Tailscale secret**: `apps/development/development-workspace/app/tailscale.secret.yaml`

## Intent and Design
- This app is a **generic development workspace**, not a Copilot-specific workload.
- The main container currently uses **`mcr.microsoft.com/devcontainers/base:ubuntu-24.04`** as a general-purpose Ubuntu LTS-based development image.
- The chart should stay broadly useful for development work: avoid hard-coding Copilot-specific startup logic or single-purpose assumptions unless explicitly requested.
- The repo still has a separate `apps/development/copilot-cli` app; do not conflate the two.

## Workspace Layout
- The persistent workspace root is **`/workspace/repos`**.
- Git repositories are configured as a list under:
  ```yaml
  git:
    repositories:
      - name: elite-flux-cluster
        url: https://github.com/fossum/elite-flux-cluster.git
        ref: main
        depth: 1
  ```
- Each repo is cloned into its own subdirectory:
  - `/workspace/repos/elite-flux-cluster`
  - `/workspace/repos/truecharts-public`
  - etc.

## Startup Behavior
- The init container is intentionally **non-destructive** for existing repositories.
- For each configured repo:
  - if `repo/.git` exists, it only verifies the directory is a Git worktree
  - if the path exists but is non-empty and not a Git repo, startup fails
  - if the path is absent, the repo is cloned
- **Do not** reintroduce `git reset --hard`, `git clean -fdx`, or automatic fetch/reset behavior on pod startup unless explicitly requested. Preserving work in progress is a core requirement.

## Storage and PVC Behavior
- The chart provisions a PVC for the repositories volume unless `existingClaim` is set.
- **Do not define a default storage class** in the chart. `storageClassName` should remain empty by default.
- The HelmRelease may set PVC size, but should avoid forcing a storage class unless specifically requested for that deployment.

## Tailscale
- The workspace includes a **Tailscale sidecar**.
- The auth key is read from:
  - **Secret name**: `development-workspace-secrets`
  - **Secret key**: `TAILSCALE_AUTH_KEY`
- The encrypted placeholder secret lives at:
  - `apps/development/development-workspace/app/tailscale.secret.yaml`
- Keep the sidecar configuration generic and avoid tying it to a specific app protocol.

## Main Container Conventions
- The main workload is a long-lived interactive development container.
- Startup is configured through:
  ```yaml
  workspace:
    startupCommand:
    startupArgs:
  ```
- Prefer keeping these generic and overridable through chart values.
- If a better all-around development image is proposed, it should still remain generic; otherwise Ubuntu LTS is the fallback.

## Files Most Likely To Change
- `charts/development-workspace/values.yaml`
- `charts/development-workspace/templates/deployment.yaml`
- `charts/development-workspace/templates/pvc.yaml`
- `apps/development/development-workspace/app/helm-release.yaml`
- `apps/development/development-workspace/app/tailscale.secret.yaml`
- `apps/development/kustomization.yaml`

## Safe Change Patterns
- Add or remove repos by editing `git.repositories` in the HelmRelease values.
- Change startup behavior by editing `workspace.startupCommand` and `workspace.startupArgs`.
- Adjust storage size via `persistence.repositories.size`.
- Keep the workspace root under `/workspace/...`; the init logic validates this.
- If renaming the app or chart, update **both** the app path and the local chart path consistently.

## Validation
- Render the local chart:
  ```bash
  helm template development-workspace charts/development-workspace
  ```
- Render the repo manifests:
  ```bash
  kubectl kustomize apps
  ```

## Common Mistakes To Avoid
- Reintroducing Copilot-specific behavior into the generic workspace chart
- Hard-coding a storage class in the chart defaults
- Resetting or cleaning Git repositories during startup
- Collapsing multi-repo support back to a single checkout
- Editing `apps/development/copilot-cli` when the request is about the generic development workspace
