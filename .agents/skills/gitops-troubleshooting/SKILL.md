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
* **Resolution, cheapest first**:
  1. If you've since pushed a **new commit** that fixes the underlying cause, a plain
     `flux reconcile helmrelease -n <namespace> <release-name>` (no `--with-source` needed if the
     source already synced) is often enough — it force-triggers a fresh reconcile attempt outside
     the normal retry/backoff bookkeeping and can clear a `Stalled: MissingRollbackTarget` state
     even while `status.observedGeneration` still shows the old generation for a few seconds.
     Cheaper and less disruptive than the options below; try it before reaching for suspend/resume
     or secret deletion.
  2. If that doesn't unstick it: delete the failed release secrets from the target namespace if
     present.
  3. Clear the stalled status and reset the failures counter in the Helm controller by suspending and immediately resuming the release:
     ```bash
     flux suspend helmrelease -n <namespace> <release-name>
     flux resume helmrelease -n <namespace> <release-name>
     ```

### C. `flux reconcile ... --with-source` CLI timeout ≠ actual failure
* **Symptom**: `flux reconcile helmrelease <name> -n <namespace> --with-source` prints
  `✗ context deadline exceeded` and returns, but the release is still healthy or still genuinely
  progressing when you check `kubectl get helmrelease`.
* **Root Cause**: The `flux` CLI's own client-side wait for the reconcile to *finish* has a short
  timeout unrelated to the HelmRelease's own `spec.upgrade.timeout` (which can be much longer, e.g.
  `60m`). The actual `helm upgrade` operation keeps running server-side inside `helm-controller`
  regardless of whether the CLI gave up waiting.
* **Resolution**: don't treat CLI timeout as failure. Poll `kubectl get helmrelease -n <namespace>
  <name>` / `.status.conditions[?(@.type=="Ready")]` directly instead of trusting the `flux
  reconcile` command's own exit/output.

### D. `ttlSecondsAfterFinished` Jobs can fail a long-running Helm `--wait` with a false "not found"
* **Symptom**: A `helm upgrade` that otherwise looks like it's progressing normally (all real
  workload pods healthy) eventually fails with `jobs.batch "<name>-<hash>" not found`, and this
  repeats across retries with a *different* hash each time.
* **Root Cause**: The chart includes a plain (non-hook) `Job` with `ttlSecondsAfterFinished` set to
  something shorter than the overall release's `--wait` duration. If the Job finishes quickly but
  the rest of the release takes long enough (large image pulls, other slow-to-ready resources),
  Kubernetes garbage-collects the finished Job via its TTL before Helm's own polling loop gets back
  around to checking it, and Helm reports the resource as unexpectedly missing rather than
  successfully completed.
* **Resolution**: this isn't something you can wait out — it will keep recurring on retries as
  long as the release takes longer than the Job's TTL. Fix the actual reason the overall release is
  slow (or, if the Job's function isn't needed at all in this cluster, disable whatever chart
  feature creates it).

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

---

## 5. K3s ServiceLB (klipper-lb) Port Hijack & Host SSH Lockout

### Symptoms
* Attempting to SSH to a node's physical LAN IP (`ssh <node-ip>`) prompts with an unexpected ED25519 host key fingerprint (e.g. matching `nobody@gitlab-shared-secrets...` or another container).
* Authentication fails with `Permission denied (publickey,keyboard-interactive)` even though valid user keys exist in the host's `~/.ssh/authorized_keys`.
* VPN/Tailscale SSH works normally (because it operates over a virtual interface), but direct LAN SSH is broken.

### Root Cause
When a Kubernetes `Service` of type `LoadBalancer` exposes port 22 (such as `gitlab-gitlab-shell` for Git SSH), K3s's built-in ServiceLB (`klipper-lb`) controller automatically deploys a DaemonSet (`svclb-*`) that binds `hostPort: 22` on every node's physical IP address. This intercepts incoming traffic on port 22 on the physical host and redirects it to the container instead of the host's OpenSSH server.

### Resolution
1. When using MetalLB or dedicated IP pools for LoadBalancers, disable K3s ServiceLB on the conflicting service by adding the annotation:
   ```yaml
   metadata:
     annotations:
       svccontroller.k3s.cattle.io/enablelb: "false"
   ```
2. Delete the rogue ServiceLB DaemonSet in `kube-system`:
   ```bash
   kubectl delete daemonset -n kube-system svclb-<service-name>-<hash>
   ```
3. Once deleted, port 22 on the physical nodes will immediately be freed back to the host operating system's `sshd`.
4. Ensure clients remove the container's cached host key fingerprint from `~/.ssh/known_hosts`:
   ```bash
   ssh-keygen -R <node-ip>
   ```

---

## 6. Kubernetes `ndots:5` DNS Search Domain Wildcard Hijacking

### Symptoms
* Workloads experience intermittent connection timeouts or connection refused when attempting to reach internal cluster services (e.g., `dial tcp <WAN-IP>:6379: i/o timeout` connecting to `redis.infrastructure.svc.cluster.local:6379`).
* The problem may appear node-dependent (working when scheduled on some nodes, failing on others).

### Root Cause
1. Kubernetes pods inherit search domains from the host's `/etc/resolv.conf` (often assigned via router DHCP, e.g. `thefoss.org`).
2. Pod `/etc/resolv.conf` defaults to `options ndots:5`. Any internal domain with fewer than 5 dots (e.g. 4-dot names like `<service>.<namespace>.svc.cluster.local`) is treated as relative, prompting the resolver to iterate through each search domain before querying the absolute name:
   `redis.infrastructure.svc.cluster.local.thefoss.org`
3. If the host search domain is a public domain with a wildcard DNS record (`*.thefoss.org -> <WAN-IP>`), public DNS returns the router's WAN IP. The resolver stops searching and attempts to connect to the external router IP instead of the internal ClusterIP.
4. If CoreDNS has a standalone `.server` block for that domain (e.g. `thefoss.server`), CoreDNS forwards the query to upstream DNS without checking Kubernetes internal service records.

### Resolution
1. **Router DHCP Domain**: Configure router DHCP option 15 to hand out a private, non-wildcard local domain (e.g. `thefoss.local` or `.internal`) instead of a public domain with wildcard records.
2. **CoreDNS Clean Overrides**: Avoid creating separate `domain.org:53` `.server` blocks in CoreDNS for local host overrides. Instead, use `custom/*.override` which injects rules inside the primary `.:53` Kubernetes zone so internal service lookups are never bypassed:
   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: coredns-custom
     namespace: kube-system
   data:
     truenas.override: |
       hosts {
           192.168.1.10 truenas.thefoss.org
           fallthrough
       }
   ```
3. **CoreDNS Safety Template**: If a `.server` block for the search domain is required, prevent relative cluster queries from leaking upstream by adding an explicit NXDOMAIN template:
   ```corefile
   template IN ANY cluster.local.<domain> {
       rcode NXDOMAIN
   }
   ```

---

## 7. Node Maintenance & Eviction with Longhorn and CNPG

### Preparing a Node for Maintenance / Disk Replacement
1. **Evacuate Longhorn Storage**:
   * Patch the Longhorn node and disk to stop scheduling and request replica eviction:
     ```bash
     kubectl -n longhorn-system patch nodes.longhorn.io <node-name> --type=merge -p '{"spec":{"allowScheduling":false,"evictionRequested":true,"disks":{"<disk-name>":{"allowScheduling":false,"evictionRequested":true}}}}'
     ```
   * Verify that replica count on the node reaches `0`:
     ```bash
     kubectl -n longhorn-system get replicas -o json | jq '[.items[] | select(.spec.nodeID=="<node-name>")] | length'
     ```
2. **Handle PodDisruptionBudgets (PDBs)**:
   * **Longhorn `instance-manager`**: Longhorn runs an `instance-manager` pod on each node with a strict `minAvailable: 1` PDB. Standard `kubectl drain` will hang or fail. Always exclude instance-manager from drain:
     ```bash
     kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --pod-selector='longhorn.io/component!=instance-manager'
     ```
   * **CloudNative-PG (CNPG)**: If a single-instance CNPG database or primary pod blocks drain via its primary PDB, temporarily disable it:
     ```bash
     kubectl patch cluster.postgresql.cnpg.io <cluster-name> -n <namespace> --type=merge -p '{"spec":{"enablePDB":false}}'
     ```
3. **Restoring the Node Post-Maintenance**:
   * Uncordon node: `kubectl uncordon <node-name>`
   * Re-enable Longhorn scheduling and disable eviction:
     ```bash
     kubectl -n longhorn-system patch nodes.longhorn.io <node-name> --type=merge -p '{"spec":{"allowScheduling":true,"evictionRequested":false,"disks":{"<disk-name>":{"allowScheduling":true,"evictionRequested":false}}}}'
     ```
   * Restore CNPG PDBs:
     ```bash
     kubectl patch cluster.postgresql.cnpg.io <cluster-name> -n <namespace> --type=merge -p '{"spec":{"enablePDB":true}}'
     ```

