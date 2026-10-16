---
name: truecharts-helm
description: Guidelines and constraints for developing and modifying Helm charts using the TrueCharts common library.
---

# TrueCharts common library development guidelines

When developing or modifying Helm charts that use the TrueCharts common library (`common` dependency), adhere to the following rules:

## 1. Hard-coded mount paths in persistence configuration
> [!IMPORTANT]
> The `mountPath` configured under `persistence` must be a static, hard-coded string (e.g. `/srv/outputs` or `/srv/inputs`).
> 
> Do **NOT** use dynamic Helm template expressions referencing container environment variables (e.g., `'{{ .Values.workload.main.podSpec.containers.main.env.VAR }}'`). While this might render during basic `helm template` checks, it fails during cluster deployment/reconciliation.

## 2. SecurityContext overrides for Selenium/Chrome or similar workloads
If a container uses Selenium, ChromeDriver, Xvfb, or any workloads requiring display buffers or write permissions:
- You must override TrueCharts' default strict securityContext.
- Set container `runAsUser` and `runAsGroup` to `0` (root) and `readOnlyRootFilesystem` to `false` in `values.yaml` if needed:
  ```yaml
  securityContext:
    container:
      runAsUser: 0
      runAsGroup: 0
      readOnlyRootFilesystem: false
  ```

## 3. Primary Service Requirement
TrueCharts enforces that at least one enabled service must be marked as primary (`primary: true`).
- Disabling `service.main` (`service.main.enabled: false`) without explicitly setting `primary: true` on an alternative service will crash chart rendering with:
  ```
  execution error at (.../common.yaml): Service - At least one enabled service must be primary
  ```
- If an application uses an alternative service for ingress or external traffic, prefer keeping `service.main.enabled: true` with `type: ClusterIP` rather than setting `enabled: false`.

## 4. `nodeSelector` vs `affinity.nodeAffinity`
- TrueCharts common library (`_affinity.tpl`) will fail Helm template rendering with `fail "TODO: not implemented"` if `affinity.nodeAffinity` is passed via values.
- To schedule or pin pods, always use `podOptions.nodeSelector` or `workload.<workload-name>.podSpec.nodeSelector`.

## 5. MetalLB Shared IPs & Custom Chart LoadBalancers
- **Sharing Keys**: MetalLB only allows multiple services to share a single IP if they declare matching `metallb.io/allow-shared-ip` annotations and non-conflicting ports/protocols.
- **Custom Charts**: When authoring or configuring custom Helm charts with `type: LoadBalancer` (e.g. `ib-gateway`), always template `loadBalancerIP: {{ .Values.service.loadBalancerIP }}`. Without an explicit IP, MetalLB will auto-assign the lowest available IP from the pool (e.g. `192.168.1.151`), potentially conflicting with statically-addressed services like Valheim.

