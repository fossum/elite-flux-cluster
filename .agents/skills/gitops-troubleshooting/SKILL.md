---
name: gitops-troubleshooting
description: Playbooks and instructions for diagnosing and clearing cluster-wide GitOps deadlocks, stuck HelmReleases, admission webhook blockages, and host sysctl inotify watches/instances limits.
---

# GitOps & Cluster Troubleshooting Playbook

This guide contains step-by-step instructions for diagnosing and resolving complex Kubernetes GitOps deadlocks, stuck Helm releases, webhook blockages, and host sysctl limits in this repository.

---

## 1. Flux CD & Helm Controller Deadlocks

### A. CSI & PVC Queue Deadlock
* **Symptom**: A HelmRelease with `spec.wait: true` is stuck in `Progressing` or `pending-install` status, and the `helm-controller` queue is completely blocked.
* **Root Cause**: The HelmRelease is queued *before* its storage provider's CSI driver (e.g., `truenas-nfs` or `truenas-iscsi`). The consumer pod is waiting for a PVC, which is waiting for the CSI driver to provision it, but the CSI driver installation is queued *behind* the waiting release.
* **Resolution**:
  1. Identify the blocked consumer HelmRelease and suspend it:
     ```bash
     flux suspend helmrelease -n <namespace> <release-name>
     ```
  2. Rollout restart the `helm-controller` deployment to clear its in-memory queue:
     ```bash
     kubectl rollout restart deployment -n flux-system helm-controller
     ```
  3. Wait for the CSI driver provider's HelmRelease to complete installation successfully.
  4. Resume the suspended consumer HelmRelease:
     ```bash
     flux resume helmrelease -n <namespace> <release-name>
     ```

### B. Webhook Admission Deadlock
* **Symptom**: When deleting/pruning a namespace holding webhook servers (like `cert-manager` or `cloudnative-pg`), the namespace is stuck terminating, and all new API resource creations fail with admission or validation webhook connection errors.
* **Root Cause**: The operator namespace was deleted, but global webhook configuration objects still refer to the offline webhook services. The Kubernetes API server redirects all creation/validation requests to these offline webhooks, blocking all API operations.
* **Resolution**:
  1. List global webhook configurations:
     ```bash
     kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations -A
     ```
  2. Delete the specific stuck configurations (e.g., `cert-manager-webhook`, `cnpg-validating-webhook-configuration`):
     ```bash
     kubectl delete validatingwebhookconfiguration <name>
     kubectl delete mutatingwebhookconfiguration <name>
     ```
  3. The API server will immediately unblock, allowing the namespace termination to complete and letting Flux recreate the operators.

### C. Re-binding Released PersistentVolumes (Retain Reclaim Policy)
* **Symptom**: An application PVC is deleted or re-created during a GitOps update, and Kubernetes provisions a new blank volume while the old volume becomes `Released`.
* **Root Cause**: The volume reclaim policy was set to `Retain` (or default), leaving the old PV untouched in a `Released` state bound to a non-existent PVC UID.
* **Resolution**:
  1. Clear the stale `claimRef` on the Released PV to make it `Available`:
     ```bash
     kubectl patch pv <pv-name> -p '{"spec":{"claimRef":null}}'
     ```
  2. If the volume was attached to a different node via CSI, delete any stale VolumeAttachment:
     ```bash
     kubectl delete volumeattachment <attachment-name>
     ```
  3. Re-create the PVC specifying `volumeName: <pv-name>`:
     ```yaml
     apiVersion: v1
     kind: PersistentVolumeClaim
     metadata:
       name: <pvc-name>
       namespace: <namespace>
     spec:
       accessModes: [ReadWriteOnce]
       resources: { requests: { storage: <size> } }
       storageClassName: <storage-class>
       volumeName: <pv-name>
     ```

---

## 2. Unblocking Stuck Helm Releases

### A. Stuck `pending-upgrade` or `pending-install` Status
* **Symptom**: A `flux get helmreleases` shows `READY: Unknown` with message `Running 'upgrade' action`, but the release has been stuck for much longer than the timeout period. Checking `helm list` shows status `pending-upgrade` or `pending-install`.
* **Root Cause**: The previous upgrade/install action was interrupted (e.g., due to pod rescheduling, host eviction, or controller restarts), leaving a lock on the Helm release secrets.
* **Resolution**:
  1. Find the secrets tracking Helm release revisions in the target namespace:
     ```bash
     kubectl get secrets -n <namespace> | grep sh.helm.release
     ```
  2. Delete the secret corresponding to the stuck revision (e.g., the highest revision number):
     ```bash
     kubectl delete secret -n <namespace> sh.helm.release.v1.<release-name>.v<revision-number>
     ```
  3. Once deleted, Helm will revert to the last known completed revision, unlocking the release.

### B. Stalled Releases / Max Retries Exceeded
* **Symptom**: A HelmRelease fails with the message `terminal error: exceeded maximum retries: cannot remediate failed release` or `stalled resources`. Flux refuses to retry the release even after annotations are updated.
* **Root Cause**: The release reached its maximum remediation failure count in the `HelmRelease.status.failures` field.
* **Resolution**:
  1. Delete the failed release secrets from the target namespace if present.
  2. Clear the stalled status and reset the failures counter in the Helm controller by suspending and immediately resuming the release:
     ```bash
     flux suspend helmrelease -n <namespace> <release-name>
     flux resume helmrelease -n <namespace> <release-name>
     ```

---

## 3. Host sysctl `fs.inotify` Watch/Instance Limits

* **Symptom**: Logging daemons (like `promtail`) or system controllers (like `intel-gpu-plugin`) crash loop with errors like `Failed to create watcher: too many open files` or `Failed to serve: too many open files`.
* **Root Cause**: The host Linux kernel's default inotify limits (`fs.inotify.max_user_watches` and `fs.inotify.max_user_instances`) are too low to handle the volume of files and socket descriptors being monitored by all pods on the node.
* **Resolution**:
  1. Rather than manual host updates, deploy a privileged `DaemonSet` to automatically set the limits across all current and future nodes:
     ```yaml
     apiVersion: apps/v1
     kind: DaemonSet
     metadata:
       name: sysctl-setter
       namespace: kube-system
     spec:
       selector:
         matchLabels:
           name: sysctl-setter
       template:
         metadata:
           labels:
             name: sysctl-setter
         spec:
           hostPID: true
           hostNetwork: true
           initContainers:
           - name: sysctl-setter
             image: alpine:latest
             securityContext:
               privileged: true
             command:
             - sh
             - -c
             - |
               sysctl -w fs.inotify.max_user_instances=1024
               sysctl -w fs.inotify.max_user_watches=1048576
           containers:
           - name: pause
             image: registry.k8s.io/pause:3.10
     ```
  2. Once the DaemonSet successfully rolls out, delete the crashlooping pods to let them initialize with the new host limits.

---

## 4. TypeScript Applications on Shared Volumes

### A. Bypassing Git Pulls on Startup
* **Symptom**: Pods mounting a shared PVC (containing the code checkout) fail to start up due to git clone/pull errors (`fatal: could not read Username` or `502 Bad Gateway` from GitLab).
* **Root Cause**: The entrypoint script is configured to check `PULL_REPO` and pull/clone code on every startup, which fails if GitLab is empty (e.g. database reset) or offline.
* **Resolution**:
  1. Unset the `PULL_REPO` environment variable entirely by removing it from the chart's defaults (`values.yaml`) or HelmReleases.
  2. Many entrypoint scripts check `[ ! -z "$PULL_REPO" ]` (non-empty/defined), so setting it to `"false"` is still treated as "set" and triggers a pull. It **must** be completely deleted or left empty (`""`).

### B. Traps with Bundled Executables (.ts vs .cjs)
* **Symptom**: A TypeScript Node app compiles successfully on startup but exits immediately with exit code `0` and enters a crash loop.
* **Root Cause**: The main application script contains an entrypoint guard:
  ```typescript
  if (process.argv[1] && process.argv[1].endsWith('engine.ts')) { ... }
  ```
  When the application is bundled/compiled to JavaScript (`dist/engine.cjs`), `process.argv[1]` ends with `engine.cjs`, so the entrypoint check fails, causing the app to silently terminate without starting its servers or manager loops.
* **Resolution**:
  Update the check to support both development (.ts) and production bundle (.cjs) extensions:
  ```typescript
  if (process.argv[1] && (process.argv[1].endsWith('engine.ts') || process.argv[1].endsWith('engine.cjs')))
  ```
