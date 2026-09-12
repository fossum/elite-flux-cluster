---
name: pod-timeout-recovery-generic
description: Generic troubleshooting and recovery workflow for pod rollout timeouts, probe failures, and helm upgrade deadline errors.
---

# Pod Timeout Recovery Skill (Generic)

## When To Use This Skill
- Helm/Kustomization reports `context deadline exceeded`.
- Pod rollouts stall or flap.
- Probes fail repeatedly and upgrades roll back.

## Target Variables
```bash
NS=<namespace>
WORKLOAD_KIND=<deployment|statefulset|daemonset>
WORKLOAD_NAME=<name>
```

## Triage Workflow
1. Determine whether timeout is pre-start (scheduling/attach), startup (container boot), or readiness/probe phase.
2. Inspect rollout status and event timeline.
3. Check container logs (current and previous) for first fatal signal.
4. Apply the smallest phase-specific fix.

## Diagnostic Commands
### 1) Rollout and pod state
```bash
kubectl -n "$NS" get "$WORKLOAD_KIND" "$WORKLOAD_NAME" -o wide
kubectl -n "$NS" rollout status "$WORKLOAD_KIND"/"$WORKLOAD_NAME"
kubectl -n "$NS" get pods -l app.kubernetes.io/instance="$WORKLOAD_NAME" -o wide
```

### 2) Events and probe failures
```bash
kubectl -n "$NS" get events --sort-by=.lastTimestamp
kubectl -n "$NS" describe pod <pod-name>
```

### 3) Logs
```bash
kubectl -n "$NS" logs <pod-name> --all-containers --tail=300
kubectl -n "$NS" logs <pod-name> --all-containers --previous --tail=300
```

## Typical Fixes by Failure Phase
- Scheduling/attach issues: resolve node, PVC/PV, or image pull blockers first.
- Startup failures: fix command/env/config errors before probe tuning.
- Probe-only failures: increase startup grace (`initialDelaySeconds`, `failureThreshold`) and align readiness with app boot time.
- Controller timeout too short: increase HelmRelease timeout for slow upgrades.

## Validation Checklist
- New pod reaches Running and Ready.
- Restarts stop increasing.
- Rollout status succeeds.
- Controller condition transitions to Ready/UpgradeSucceeded.

## Common Mistakes
- Increasing timeouts before fixing obvious container startup errors.
- Reading only current logs when crash evidence is in previous logs.
- Treating a healthy old replica as proof new rollout succeeded.
