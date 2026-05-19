---
name: prometheus
description: Prometheus, Alertmanager, and kube-prometheus-stack troubleshooting guide for the elite-flux-cluster. Use this when asked about monitoring, alerts, Flux health metrics, or K3s-specific Prometheus behavior.
---

# Prometheus Troubleshooting Skill — elite-flux-cluster

## Deployment Overview
- **Chart**: `prometheus-community/kube-prometheus-stack`
- **Namespace**: `infrastructure`
- **HelmRelease**: `apps/infrastructure/prometheus/app/helm-release.yaml`
- **Flux Kustomization**: `apps/infrastructure/observability/ks.yaml`
- **Flux path**: `apps/infrastructure/observability/app`
- **App Kustomization**: `apps/infrastructure/observability/app/kustomization.yaml`
- **Prometheus manifests**: still live under `apps/infrastructure/prometheus/app`
- **Extra monitors**:
  - `apps/infrastructure/prometheus/app/flux-podmonitor.yaml`
  - `apps/infrastructure/prometheus/app/cert-manager-podmonitor.yaml`
- **Grafana**: disabled inside the Prometheus stack; this repo manages Grafana separately in `apps/web-services/grafana`

## Key Repo Conventions
- The HelmRelease uses `kustomize.toolkit.fluxcd.io/substitute: enabled`, so `${VAR}` substitution is expected directly in `values`.
- Do **not** reintroduce a `valuesFrom` reference to `cluster-config` in this HelmRelease. That ConfigMap lives in `flux-system`, not `infrastructure`, and it previously blocked reconciliation.
- Keep Alertmanager's `null` receiver in the config. kube-prometheus-stack still routes `Watchdog` to `null` by default.

## K3s-Specific Alerting
- `KubeControllerManagerDown`, `KubeSchedulerDown`, and the default `KubeVersionMismatch` rules are disabled because K3s does not expose those components the same way as a standard control plane.
- This repo replaces the generic version-skew rule with `K3sControlPlaneVersionMismatch`, based on `kubernetes_build_info{job="apiserver"}`.
- The intent is to adapt alerts to K3s semantics, not to suppress real control-plane problems wholesale.

## Extra Monitoring Coverage
- `kube-state-metrics` is extended with `customResourceState` for Flux resources and RBAC to read them.
- Flux health alerts use `gotk_resource_info` and fire `FluxResourceNotReady` when Flux objects stay not-ready for 10 minutes.
- cert-manager scraping is added through a PodMonitor, with alerts for:
  - `CertManagerCertificateNotReady`
  - `CertManagerCertificateExpiringSoon`
- CloudNativePG alerting includes `CloudNativePGReplicationLagHigh`.

## Expected Alert Behavior
- `Watchdog` should always be firing. It is the normal heartbeat alert for the notification pipeline.
- Discord `429` responses from Alertmanager usually mean too many alert groups are firing at once, not that Discord delivery is misconfigured.

## Common Failure Modes

### HelmRelease fails to reconcile
- **Symptom**: `infrastructure/prometheus` stays `Ready=False`.
- **Likely cause**: an invalid `valuesFrom` lookup for `cluster-config`.
- **Fix**: remove the broken `valuesFrom` usage and rely on Flux substitution already enabled on the HelmRelease.

### Flux `observability` Kustomization fails with `path not found`
- **Symptom**: `flux-system/observability` stays `Ready=False` with `apps/infrastructure/observability/app: no such file or directory`.
- **Cause**: the Flux Kustomization was renamed to `observability`, but the repo still only exposed `apps/infrastructure/prometheus/app`.
- **Fix**:
  - keep `apps/infrastructure/observability/ks.yaml` pointing at `apps/infrastructure/observability/app`
  - keep `apps/infrastructure/observability/app/kustomization.yaml` as the wrapper over `../../prometheus/app`
  - do not point the live Flux Kustomization at `apps/infrastructure/prometheus/app`

### Alertmanager fails with `undefined receiver "null"`
- **Cause**: custom `alertmanager.config.receivers` removed the `null` receiver while the chart still referenced it from the default route tree.
- **Fix**: restore:
  ```yaml
  receivers:
    - name: 'null'
  ```

### K3s ingress ServiceLB alerts (`svclb-*`)
- **Symptoms**:
  - `KubePodNotReady`
  - `KubeDaemonSetRolloutStuck`
  - pending `svclb-*ingress-nginx*` pods in `kube-system`
- **Root cause**: both internal and external LoadBalancer Services expose `80/443`; if they target the same nodes, K3s ServiceLB creates unschedulable pods due to host-port conflicts.
- **Fix pattern**:
  - put ServiceLB in allow-list mode with `svccontroller.k3s.cattle.io/enablelb=true` on intended nodes
  - split ingress services into pools with `svccontroller.k3s.cattle.io/lbpool=<pool>` on nodes and matching Service labels
- **Important**: those ingress Services may be managed outside this repo, so live-cluster inspection may be required.

### Large batches of failed-job alerts
- Some `KubeJobFailed` alerts can come from stale historical Jobs rather than active breakage.
- Verify the Jobs are safe to remove before deleting them; K3s-managed bootstrap Jobs such as `helm-install-traefik*` may legitimately reappear.

## Useful Commands
```bash
# Reconcile the repo source and Prometheus release
flux reconcile source git cluster -n flux-system
flux reconcile kustomization observability -n flux-system
flux reconcile helmrelease prometheus -n infrastructure

# Check Flux and Helm state
kubectl get kustomization -n flux-system observability
kubectl describe kustomization -n flux-system observability
kubectl get helmrelease -n infrastructure prometheus
kubectl describe helmrelease -n infrastructure prometheus

# Inspect monitoring resources managed in-repo
kubectl get podmonitor,prometheusrule -n infrastructure

# Check K3s ServiceLB state during ingress alert investigations
kubectl get daemonset,pods -n kube-system | grep svclb

# Port-forward Prometheus and inspect current alerts
kubectl port-forward -n infrastructure svc/prometheus-operated 9090
curl -s http://127.0.0.1:9090/api/v1/alerts
```
