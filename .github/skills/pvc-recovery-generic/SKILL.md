---
name: pvc-recovery-generic
description: Generic recovery workflow for PVC/PV attach, mount, and binding failures causing pods to remain Pending or ContainerCreating.
---

# PVC Recovery Skill (Generic)

## When To Use This Skill
- Pod stuck in `Pending` or `ContainerCreating`.
- Events show `FailedAttachVolume`, `Multi-Attach`, or mount timeouts.
- Stateful rollout fails with context deadline exceeded.

## Target Variables
```bash
NS=<namespace>
POD=<pod-name>
PVC=<pvc-name>
PV=<pv-name>
```

## Workflow
1. Identify exact storage failure from events.
2. Verify PVC, PV, StorageClass, and attachment state.
3. Confirm which node currently has the volume attached.
4. Recover stale attachment safely.
5. Re-verify pod scheduling, mount, and readiness.

## Diagnostic Commands
### 1) Pod and events
```bash
kubectl -n "$NS" describe pod "$POD"
kubectl -n "$NS" get events --sort-by=.lastTimestamp
```

### 2) PVC and PV
```bash
kubectl -n "$NS" get pvc "$PVC" -o yaml
kubectl get pv "$PV" -o yaml
```

### 3) VolumeAttachment state
```bash
kubectl get volumeattachments.storage.k8s.io -o yaml
```

### 4) Find pods referencing a PVC
```bash
kubectl get pods -A -o json | jq -r \
  --arg pvc "$PVC" '.items[] | select(any(.spec.volumes[]?; .persistentVolumeClaim.claimName==$pvc)) | "\(.metadata.namespace)/\(.metadata.name) node=\(.spec.nodeName) phase=\(.status.phase)"'
```

## Safe Recovery Pattern
1. Ensure only intended pod should use the PVC.
2. If a stale VolumeAttachment exists on a different node, delete that stale attachment object.
3. Watch for new attach and pod transition to Running.

Example:
```bash
kubectl delete volumeattachment.storage.k8s.io <stale-volumeattachment-name>
kubectl -n "$NS" get pod "$POD" -w
```

## Validation Checklist
- Pod is Running and Ready.
- Attach/mount events are successful.
- VolumeAttachment points to correct node.
- App endpoints are healthy.

## Common Mistakes
- Deleting active attachment used by healthy running workload.
- Ignoring access mode (`ReadWriteOnce` vs `ReadWriteMany`).
- Treating PVC Bound status alone as proof that mounts are healthy.
