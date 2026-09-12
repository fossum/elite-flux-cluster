---
name: loadbalancer-ip-reconcile
description: Generic troubleshooting and remediation guide for LoadBalancer IP changes that do not apply in the elite-flux-cluster, across plain Services, Helm-managed apps, and operator-managed child Services.
---

# LoadBalancer IP Reconcile Skill - elite-flux-cluster

## When To Use This Skill
- A Service of type LoadBalancer stays on an old IP after Git changes.
- Flux shows healthy/applied revision, but the live external IP is unchanged.
- A chart or operator shows desired state updated, but child Service state does not match.
- MetalLB allocation appears stuck or ignores requested IP.

## Cluster Context
- **GitOps engine**: FluxCD
- **Load balancer controller**: MetalLB
- **Applies to**: plain Services, Helm-managed Services, and operator-managed child Services (for example CNPG, app operators, or custom controllers).

## Target Variables
Set these before running commands so the workflow is reusable:

```bash
NS=<namespace>
SVC=<service-name>
WANT_IP=<desired-ip>
FLUX_KS=<flux-kustomization-name>
```

Optional when troubleshooting operator-managed child Services:

```bash
PARENT_KIND=<resource-kind>
PARENT_NAME=<resource-name>
```

## Typical Source Files
- `apps/<namespace>/<app>/app/*.yaml`
- `apps/<namespace>/<app>/ks.yaml`
- `apps/<namespace>/kustomization.yaml`
- `apps/kustomization.yaml`

## Fast Triage Workflow
1. Confirm desired IP in Git manifest(s).
2. Confirm Flux applied the revision containing that change.
3. Inspect live Service `spec.loadBalancerIP` versus `status.loadBalancer.ingress[0].ip`.
4. Validate MetalLB IP pool contains the desired IP and no conflicts exist.
5. If parent resource updated but child Service did not, patch child Service directly.
6. Reconcile Flux again and verify persistence.

## Diagnostic Commands
### 1) Find desired IP in Git
```bash
grep -Rns "loadBalancerIP\|type:[[:space:]]*LoadBalancer" apps
```

### 2) Inspect live Service state
```bash
kubectl -n "$NS" get svc "$SVC" -o yaml
kubectl -n "$NS" describe svc "$SVC"
```
Compare:
- `spec.loadBalancerIP` (requested)
- `status.loadBalancer.ingress[0].ip` (assigned)

### 3) Compare all LoadBalancer Services
```bash
kubectl get svc -A -o jsonpath='{range .items[?(@.spec.type=="LoadBalancer")]}{.metadata.namespace}/{.metadata.name}{" spec="}{.spec.loadBalancerIP}{" status="}{.status.loadBalancer.ingress[0].ip}{"\n"}{end}'
```

### 4) Flux status and reconcile
```bash
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
flux reconcile kustomization "$FLUX_KS" -n flux-system --with-source
```

### 5) MetalLB pool validation
```bash
kubectl get ipaddresspools.metallb.io -A -o yaml
```
Verify `WANT_IP` is inside a configured pool range.

### 6) Optional: parent resource state (operator-managed Service)
```bash
kubectl -n "$NS" get "$PARENT_KIND" "$PARENT_NAME" -o yaml
```
Use this when a controller manages the Service and you need to compare parent desired state versus child actual state.

## Known Drift Pattern
A controller-managed parent resource can reflect the new desired LoadBalancer IP while the child Service remains unchanged.

Symptoms:
- Flux revision is applied and healthy.
- Parent resource spec shows `WANT_IP`.
- Child Service `status` remains old IP.
- Child Service `spec.loadBalancerIP` is empty or stale.

## Remediation
### Immediate safe fix (patch child Service)
```bash
kubectl -n "$NS" patch svc "$SVC" --type merge -p "{\"spec\":{\"loadBalancerIP\":\"$WANT_IP\"}}"
kubectl -n "$NS" get svc "$SVC" -o jsonpath='{"spec="}{.spec.loadBalancerIP}{" status="}{.status.loadBalancer.ingress[0].ip}{"\n"}'
```

Expected pattern:
- `spec=<desired-ip> status=<desired-ip>`

### Post-fix GitOps verification
```bash
flux reconcile kustomization "$FLUX_KS" -n flux-system --with-source
kubectl -n "$NS" get svc "$SVC" -o jsonpath='{"spec="}{.spec.loadBalancerIP}{" status="}{.status.loadBalancer.ingress[0].ip}{"\n"}'
```

## Validation Checklist
- Flux Kustomization is `Ready=True`.
- Desired IP in Git matches runtime requested IP (`spec.loadBalancerIP`).
- Runtime requested IP matches assigned IP (`status.loadBalancer.ingress[0].ip`).
- Desired IP is inside MetalLB pool range.
- No other LoadBalancer Service is already using the desired IP.

## Common Mistakes
- Assuming Flux healthy status means every controller-managed child object changed as expected.
- Checking only assigned status IP and not requested spec IP.
- Forgetting to reconcile the correct Flux Kustomization.
- Requesting an IP outside configured MetalLB pools.
- Reusing an IP that is already allocated to another Service.

## Escalation Path
If patching the Service does not move the IP:
1. Verify conflicts across all LoadBalancer Services.
2. Check MetalLB controller and speaker logs.
3. Verify L2/BGP advertisement path and LAN reachability.
4. Recreate only the affected Service if approved (brief interruption possible).

## Optional CNPG Example
For CNPG additional managed Services, the parent `Cluster` may contain desired updates while the child Service remains stale. In that case, use the same workflow above and patch the child Service directly if needed.
