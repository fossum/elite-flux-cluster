---
name: flux-gitops-reconcile-generic
description: Generic FluxCD troubleshooting and reconcile workflow for source, kustomization, and helmrelease drift.
---

# Flux GitOps Reconcile Skill (Generic)

## When To Use This Skill
- Source changes are not reflected in the cluster.
- Resources are healthy but do not match expected values.
- HelmRelease or Kustomization is stuck in progressing or retry loops.
- Live hotfixes are reverted unexpectedly.

## Core Principle
Flux applies committed source revisions, not local uncommitted edits.

## Target Variables
```bash
KS=<kustomization-name>
KS_NS=<kustomization-namespace>
HR=<helmrelease-name>
HR_NS=<helmrelease-namespace>
GIT_SRC=<gitrepository-name>
SRC_NS=<source-namespace>
```

## Workflow
1. Confirm source revision and controller status.
2. Confirm resource generation/observedGeneration alignment.
3. Reconcile in dependency order.
4. Verify runtime state and conditions.

## Diagnostic Commands
### 1) Source status
```bash
kubectl -n "$SRC_NS" get gitrepository "$GIT_SRC" -o yaml
```

### 2) Kustomization status
```bash
kubectl -n "$KS_NS" get kustomization "$KS" -o yaml
```

### 3) HelmRelease status
```bash
kubectl -n "$HR_NS" get helmrelease "$HR" -o yaml
```

### 4) Controller logs
```bash
flux logs --all-namespaces | grep -Ei "error|failed|$KS|$HR"
```

## Reconcile Order
```bash
flux reconcile source git "$GIT_SRC" -n "$SRC_NS"
flux reconcile kustomization "$KS" -n "$KS_NS" --with-source
flux reconcile helmrelease "$HR" -n "$HR_NS"
```

## Drift Notes
- `--with-source` may overwrite ad-hoc live patches not present in source.
- Use reconcile without `--with-source` for temporary live-only adjustments.

## Validation Checklist
- `Ready=True` on source, Kustomization, and HelmRelease.
- `observedGeneration` catches up to `metadata.generation`.
- Applied revision matches expected source revision.
- Runtime object fields match desired values.

## Common Mistakes
- Reconciling the wrong Kustomization or namespace.
- Forgetting source reconciliation before downstream objects.
- Treating local workspace edits as deployable state.
