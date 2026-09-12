---
name: metallb-ip-reconcile-generic
description: Generic troubleshooting and remediation guide for MetalLB LoadBalancer IP drift, allocation failures, and conflicts across plain Services and controller-managed Services.
---

# MetalLB IP Reconcile Skill (Generic)

## When To Use This Skill
- A Service stays on the wrong external IP after config changes.
- A requested static IP is not assigned.
- MetalLB shows allocation or conflict errors.
- A parent controller appears updated, but child Service IPs do not match.

## Target Variables
Set these before running commands:

```bash
NS=<namespace>
SVC=<service-name>
WANT_IP=<desired-ip>
FLUX_KS=<kustomization-name>
```

Optional for controller-managed children:

```bash
PARENT_KIND=<resource-kind>
PARENT_NAME=<resource-name>
```

## Fast Workflow
1. Confirm desired IP in source manifests.
2. Compare live Service requested vs assigned IP.
3. Check for duplicate use of WANT_IP across all LoadBalancer Services.
4. Validate WANT_IP is in a MetalLB pool.
5. Reconcile controller and verify persistence.

## Diagnostic Commands
### 1) Find desired IP in source
```bash
grep -Rns "loadBalancerIP\|type:[[:space:]]*LoadBalancer" .
```

### 2) Inspect Service state
```bash
kubectl -n "$NS" get svc "$SVC" -o yaml
kubectl -n "$NS" describe svc "$SVC"
```

Key fields:
- `spec.loadBalancerIP` (requested)
- `status.loadBalancer.ingress[0].ip` (assigned)

### 3) Find collisions
```bash
kubectl get svc -A -o jsonpath='{range .items[?(@.spec.type=="LoadBalancer")]}{.metadata.namespace}/{.metadata.name}{" spec="}{.spec.loadBalancerIP}{" status="}{.status.loadBalancer.ingress[0].ip}{"\n"}{end}'
```

### 4) Check MetalLB pools and events
```bash
kubectl get ipaddresspools.metallb.io -A -o yaml
kubectl get events -A --sort-by=.lastTimestamp | grep -i metallb
```

### 5) Optional parent check
```bash
kubectl -n "$NS" get "$PARENT_KIND" "$PARENT_NAME" -o yaml
```

## Remediation
### Safe immediate fix
```bash
kubectl -n "$NS" patch svc "$SVC" --type merge -p "{\"spec\":{\"loadBalancerIP\":\"$WANT_IP\"}}"
kubectl -n "$NS" get svc "$SVC" -o jsonpath='{"spec="}{.spec.loadBalancerIP}{" status="}{.status.loadBalancer.ingress[0].ip}{"\n"}'
```

### If using MetalLB annotations
Use either `spec.loadBalancerIP` or MetalLB IP annotations consistently, not both.

## Post-Fix Validation
- No `AllocationFailed` or collision events for the Service.
- Service requested IP equals assigned IP.
- Desired source state matches runtime after reconcile.
- No other Service uses the same static IP.

## Common Mistakes
- Checking only status IP and not requested spec IP.
- Reusing an already allocated static IP.
- Requesting an IP outside any pool.
- Assuming parent/controller status guarantees child Service mutation.
