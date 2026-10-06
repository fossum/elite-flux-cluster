---
name: kubernetes-debugging
description: Troubleshooting Kubernetes workloads, Helm release locks, ConfigMap sync behavior, and permission preservation inside containers. Use this when debugging stuck Helm releases, container crash loops, working directory defaults, or permission errors in startup scripts.
---

# Kubernetes Workload & Helm Debugging Skill — elite-flux-cluster

## Stuck Helm Releases (pending-upgrade)
- **Symptom**: `helm upgrade` fails with:
  ```
  Error: UPGRADE FAILED: another operation (install/upgrade/rollback) is in progress
  ```
- **Cause**: Concurrent modification of a Helm release by Flux's `helm-controller` and manual `helm upgrade` runs, leaving a lock in the cluster.
- **Resolution**:
  1. Find the release secret for the failing revision:
     ```bash
     kubectl get secrets -n <namespace> | grep sh.helm.release
     ```
  2. The latest revision will have a status label set to `pending-upgrade`.
  3. Temporarily suspend the Flux `HelmRelease` so it doesn't try to lock it again:
     ```bash
     kubectl patch hr <release-name> -n <namespace> --type=merge -p '{"spec":{"suspend":true}}'
     ```
  4. Delete the stuck secret representing the pending release:
     ```bash
     kubectl delete secret -n <namespace> sh.helm.release.v1.<release-name>.<revision>
     ```
  5. Rerun your manual Helm upgrade or wait, then resume Flux:
     ```bash
     kubectl patch hr <release-name> -n <namespace> --type=merge -p '{"spec":{"suspend":false}}'
     ```

## ConfigMap Synchronization & Pod Auto-Restarts
- **Symptom**: ConfigMap contents are modified in Helm, but the running Pod does not use the updated scripts/configurations, or continues crash-looping with the old logic.
- **Cause**: Kubernetes mounts ConfigMaps as files, but does not restart containers when those files change. If your startup logic executes at boot time, it won't pick up the changes without a pod restart.
- **Best Practice**: Add a checksum of the ConfigMap to the Pod template annotations in `deployment.yaml`:
  ```yaml
  spec:
    template:
      metadata:
        annotations:
          checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
  ```
  This ensures any modification to the ConfigMap changes the Pod template, automatically triggering a rolling update to recreate the pods with the fresh configuration.

## Preserving File Ownership and Permissions in Containers
- **Symptom**: Modifying system files like `/etc/passwd`, `/etc/shadow`, `/etc/gshadow`, or `/etc/sudoers.d/` inside a container (e.g., to custom-configure usernames) causes `sudo` or PAM authentication to fail with errors like:
  ```
  unix_chkpwd: could not obtain user info
  sudo: account validation failure, is your account locked?
  ```
- **Cause**: Tools like `sed -i` write a new file and replace the original. This resets the file group ownership to `root:root` and uses default umask permissions. For security-sensitive files (like `/etc/shadow` which requires `shadow` group access for PAM helper tools, or `/etc/sudoers.d/` which requires `0440` mode), this breaks access permissions.
- **Fix Pattern**: Use a helper function that reads the permissions and owner/group before editing and restores them immediately afterward:
  ```bash
  safe_sed() {
    local file="$1"
    local expr="$2"
    if [ -f "$file" ]; then
      local perms owner
      perms=$(stat -c "%a" "$file" 2>/dev/null || echo "640")
      owner=$(stat -c "%u:%g" "$file" 2>/dev/null || echo "0:0")
      sed -i "$expr" "$file"
      chown "$owner" "$file"
      chmod "$perms" "$file"
    fi
  }
  ```
- **Delimiter Warning**: When modifying paths containing `/` characters (e.g., home directory paths), avoid using `/` as the `sed` delimiter (like `s/old/new/`). Use a different delimiter like `|` (e.g., `s|old|new|`) to prevent syntax errors.

## Interactive Terminal (exec) Working Directories
- **Symptom**: Executing into a pod with `kubectl exec -it ... -- zsh` lands you in `/` instead of the user's home or workspace directory.
- **Cause**: No `workingDir` is set in the container spec of the Pod.
- **Fix**: Specify `workingDir` in `deployment.yaml` under the main container:
  ```yaml
  workingDir: {{ .Values.workspace.home }}
  ```
