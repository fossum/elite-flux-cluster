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
