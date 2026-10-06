---
name: prometheus
description: Prometheus, Alertmanager, and kube-prometheus-stack troubleshooting guide and diagnostic tooling for the elite-flux-cluster. Use this when asked about monitoring, active alerts, scrape target failures, PromQL queries, Flux health metrics, or K3s-specific Prometheus behavior.
---

# Prometheus Troubleshooting & Diagnostic Skill — elite-flux-cluster

## Diagnostic Helper Tool
The skill includes a zero-dependency CLI script located at [`.agents/skills/prometheus/scripts/prom_tool.py`](file:///home/ericfoss/development/elite-flux-cluster/.agents/skills/prometheus/scripts/prom_tool.py).
It queries Prometheus and Alertmanager through the Kubernetes API server proxy (`kubectl get --raw`), eliminating the need for port-forwarding or relying on curl/wget inside distroless containers.

```bash
# 1. Fetch active alerts grouped by alert name & severity with resource summaries
.agents/skills/prometheus/scripts/prom_tool.py alerts

# Show verbose descriptions for alerts
.agents/skills/prometheus/scripts/prom_tool.py alerts --verbose

# 2. Inspect failing or down scrape targets with endpoint URLs and errors
.agents/skills/prometheus/scripts/prom_tool.py targets

# 3. Execute arbitrary PromQL queries directly
.agents/skills/prometheus/scripts/prom_tool.py query 'up{job="node-exporter"}'
.agents/skills/prometheus/scripts/prom_tool.py query 'gotk_resource_info{ready!="True", suspended!="true"}'
```

## Deployment Overview
- **Namespace**: `observability`
- **Flux Kustomization**: `apps/infrastructure/observability/ks.yaml`
- **Flux path**: `apps/infrastructure/observability/app`
- **Prometheus stack HelmRelease**: `apps/infrastructure/observability/app/kube-prometheus-stack.helm-release.yaml`
- **App Kustomization**: `apps/infrastructure/observability/app/kustomization.yaml`
- **Alertmanager config**: `apps/infrastructure/observability/app/alertmanager-config.secret.yaml`
- **Related releases**:
  - `apps/infrastructure/observability/app/loki.helm-release.yaml`
  - `apps/infrastructure/observability/app/promtail.helm-release.yaml`
  - `apps/infrastructure/observability/app/blackbox-exporter.helm-release.yaml`
- **Extra monitors**:
  - `apps/infrastructure/observability/app/flux-podmonitor.yaml`
  - `apps/infrastructure/observability/app/cert-manager-podmonitor.yaml`
- **Grafana**: disabled inside the Prometheus stack; this repo manages Grafana separately in `apps/web-services/grafana`

## Key Repo Conventions
- The `kube-prometheus-stack` HelmRelease uses `kustomize.toolkit.fluxcd.io/substitute: enabled`, so `${VAR}` substitution is expected directly in manifests and chart values.
- Do **not** reintroduce a `valuesFrom` reference to `cluster-config` in the HelmRelease. Flux already injects substitution values via the parent `flux-entry` Kustomization.
- Alertmanager configuration is no longer embedded in the HelmRelease. It lives in `alertmanager-config.secret.yaml`, and the HelmRelease references it with `useExistingSecret: true`.
- Keep Alertmanager's `null` receiver in the config secret. kube-prometheus-stack still routes `Watchdog` to `null` by default.

## K3s-Specific Alerting
- `KubeControllerManagerDown` and `KubeSchedulerDown` are disabled because K3s does not expose those components the same way as a standard control plane.
- `kubeControllerManager`, `kubeScheduler`, and `kubeEtcd` scraping are disabled in the stack because those targets do not exist as standalone control-plane components in this cluster.
- The intent is to adapt alerts to K3s semantics, not to suppress real control-plane problems wholesale.

## Extra Monitoring Coverage
- `kube-state-metrics` is extended with `customResourceState` for Flux resources and RBAC to read them.
- Flux health alerts use `gotk_resource_info` and fire `FluxResourceNotReady` when Flux objects stay not-ready for 10 minutes.
- cert-manager scraping is added through a PodMonitor in the `observability` namespace, with alerts for:
  - `CertManagerCertificateNotReady`
  - `CertManagerCertificateExpiringSoon`
- Flux controllers are scraped through a PodMonitor in the `observability` namespace that targets pods in `flux-system`.
- CloudNativePG alerting includes `CloudNativePGReplicationLagHigh`.
- The observability stack also deploys Loki, Promtail, and blackbox-exporter alongside Prometheus.

## Expected Alert Behavior
- `Watchdog` should always be firing. It is the normal heartbeat alert for the notification pipeline.
- Discord `429` responses from Alertmanager usually mean too many alert groups are firing at once, not that Discord delivery is misconfigured.

## Common Failure Modes

### Prometheus Pod OOMKilled
- **Symptom**: `prometheus-kube-prometheus-stack-0` crashes periodically (Exit Code 137, `Reason: OOMKilled`).
- **Cause**: The container memory limit (default 2Gi) is exceeded during TSDB compaction or heavy queries.
- **Fix**: Increase `resources.limits.memory` and `requests.memory` in `apps/infrastructure/observability/app/kube-prometheus-stack.helm-release.yaml` to 3Gi or 4Gi.

### HelmRelease fails to reconcile
- **Symptom**: `observability/kube-prometheus-stack` stays `Ready=False`.
- **Likely cause**: an invalid `valuesFrom` lookup for `cluster-config`.
- **Fix**: remove the broken `valuesFrom` usage and rely on Flux substitution already enabled on the HelmRelease.

### Flux `observability` Kustomization fails with `path not found`
- **Symptom**: `flux-system/observability` stays `Ready=False` with `apps/infrastructure/observability/app: no such file or directory`.
- **Cause**: the repo layout under `apps/infrastructure/observability/app` is missing or partially reverted.
- **Fix**:
  - keep `apps/infrastructure/observability/ks.yaml` pointing at `apps/infrastructure/observability/app`
  - keep the concrete stack manifests in `apps/infrastructure/observability/app`
  - do not point the live Flux Kustomization at the old `apps/infrastructure/prometheus/app` path

### Alertmanager fails with `undefined receiver "null"`
- **Cause**: the custom Alertmanager config in `alertmanager-config.secret.yaml` removed the `null` receiver while the default route tree still referenced it.
- **Fix**: restore:
  ```yaml
  receivers:
    - name: 'null'
  ```

### K3s ingress ServiceLB alerts (`svclb-*`)
- **Symptoms**:
  - `KubePodNotReady`
  - `KubeDaemonSetRolloutStuck`
  - pending `svclb-*` pods in `kube-system`
- **Root cause**: both internal and external LoadBalancer Services expose conflicting host ports or target nodes without required labels; if they target the same nodes, K3s ServiceLB creates unschedulable pods due to host-port conflicts.
- **Fix pattern**:
  - put ServiceLB in allow-list mode with `svccontroller.k3s.cattle.io/enablelb=true` on intended nodes
  - split ingress services into pools with `svccontroller.k3s.cattle.io/lbpool=<pool>` on nodes and matching Service labels

### Large batches of failed-job alerts
- Some `KubeJobFailed` alerts can come from stale historical Jobs rather than active breakage.
- Verify the Jobs are safe to remove before deleting them; K3s-managed bootstrap Jobs such as `helm-install-traefik*` may legitimately reappear.

### PodMonitor-based alerts never fire
- **Symptoms**:
  - `FluxResourceNotReady`, `CertManagerCertificateNotReady`, or `CertManagerCertificateExpiringSoon` never appear
  - the related metrics are missing from Prometheus
- **Likely cause**: the PodMonitors were removed from `apps/infrastructure/observability/app/kustomization.yaml`, or recreated in the wrong namespace.
- **Fix**:
  - keep the PodMonitor resources in the `observability` namespace
  - keep `flux-podmonitor.yaml` and `cert-manager-podmonitor.yaml` listed in the app kustomization

## Useful Commands
```bash
# Reconcile the repo source and observability stack
flux reconcile source git cluster -n flux-system
flux reconcile kustomization observability -n flux-system
flux reconcile helmrelease kube-prometheus-stack -n observability

# Check Flux and Helm state
kubectl get kustomization -n flux-system observability
kubectl describe kustomization -n flux-system observability
kubectl get helmrelease -n observability kube-prometheus-stack
kubectl describe helmrelease -n observability kube-prometheus-stack

# Inspect monitoring resources managed in-repo
kubectl get podmonitor,prometheusrule,probe -n observability
kubectl get secret -n observability alertmanager-config

# Check K3s ServiceLB state during ingress alert investigations
kubectl get daemonset,pods -n kube-system | grep svclb

# Raw API server proxy queries (no port-forwarding required)
kubectl get --raw /api/v1/namespaces/observability/services/kube-prometheus-stack-alertmanager:9093/proxy/api/v2/alerts
kubectl get --raw /api/v1/namespaces/observability/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/targets
kubectl get --raw "/api/v1/namespaces/observability/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=up"
```
