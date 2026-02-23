---
name: plex
description: Plex Media Server troubleshooting and configuration guide for the elite-flux-cluster. Use this when asked about Plex deployment, ingress, playback issues, or Flux reconciliation.
---

# Plex Troubleshooting Skill — elite-flux-cluster

## Deployment Overview
- **Chart**: TrueCharts `plex` (via `charts.truecharts.org`)
- **Namespace**: `media`
- **HelmRelease**: `apps/media/plex/app/helm-release.yaml`
- **Config PVC**: `plex-config` (longhorn, old — 257+ days, DO NOT delete)
- **Media**: NFS mount at `/media` from NAS
- **Plex Account**: `fossum_13` with **lifetime Plex Pass**
- **Server ID**: `d314a2f9c39c657c0c03b262d36a0395bf90376f`

## Ingress
- **Domain**: `plex.thefoss.org`
- **Class**: `external` (NGINX Inc ingress, not community)
- **TLS**: cert-manager, issuer `thefoss-le-prod`
- **Critical**: nginx terminates TLS before forwarding to Plex on port 32400. Plex must NOT require HTTPS (`requireHTTPS: false`), otherwise it sends empty responses to plain HTTP → nginx 502.

## Key Config in helm-release.yaml
```yaml
# In plexConfig section:
requireHTTPS: false          # MUST be false — nginx handles TLS
additionalAdvertiseURL: "https://plex.thefoss.org/"   # Uncommented

# In workload > main > podSpec:
# dnsPolicy: None / dnsConfig NOT needed — was a red herring
```

## Flux GitRepository Note
- The `plex` HelmRelease is managed by the **`cluster` GitRepository** in the `flux-system` namespace, NOT `flux-system` GitRepository.
- After pushing changes, you must reconcile BOTH:
  ```bash
  flux reconcile source git cluster -n flux-system
  flux reconcile helmrelease plex -n media
  ```

## Plex New-Style Agents (tv.plex.agents.*)
- `tv.plex.agents.series`, `tv.plex.agents.movie`, `tv.plex.agents.music` are **C++ built-in agents**, NOT Python plugins.
- They register asynchronously via `MediaProviderManager` which fetches `https://plex.tv/media/providers` approximately **9 seconds after pod startup**.
- **Early startup errors** like `Unable to find or create media provider for agent 'tv.plex.agents.series'` are **normal** — they occur during the initial library scan before the async registration completes. After ~9 seconds you should see: `[MediaProviderManager] Found media provider for agent provider 'tv.plex.agents.series'`
- `providers.plex.tv` has **no public DNS A record** — this is normal and not the cause of any issues.

## Playback Failure Investigation (unresolved as of 2026-02-22)
- User can log in and see library but **cannot play media**.
- `POST /playQueues` was returning 500 with `std::exception` in C++ code.
- This may be:
  1. A timing issue (playQueue called in first 9 seconds before agents register) — retry after pod has been up >15 seconds
  2. A deeper database/metadata issue
  3. The `BackgroundProcessingQueue.cpp:64` recurring error (separate crash)
- **Next steps to diagnose**:
  1. Check current Plex logs: `kubectl logs -n media -l app.kubernetes.io/name=plex --tail=100`
  2. Try playing ~15 seconds after pod restart to rule out timing
  3. Check if `POST /playQueues` still 500s after agents are registered
  4. Look for `BackgroundProcessingQueue` errors — may indicate DB corruption
  5. Check `Preferences.xml` — confirm `secureConnections=1` (not 0)

## Preferences.xml Location
```
/config/Library/Application Support/Plex Media Server/Preferences.xml
```
Key fields: `requireHTTPS`, `customConnections`, `allowedNetworks`, `PlexOnlineToken`

## Useful Commands
```bash
# Get pod
kubectl get pod -n media -l app.kubernetes.io/name=plex

# Tail logs
kubectl logs -n media -l app.kubernetes.io/name=plex -f --tail=50

# Exec into pod
kubectl exec -n media <pod> -- bash

# Read preferences
kubectl exec -n media <pod> -- cat "/config/Library/Application Support/Plex Media Server/Preferences.xml"

# Test local API
TOKEN=$(kubectl exec -n media <pod> -- grep -oP 'PlexOnlineToken="\K[^"]*' "/config/Library/Application Support/Plex Media Server/Preferences.xml")
kubectl exec -n media <pod> -- curl -s "http://localhost:32400/media/providers?X-Plex-Token=$TOKEN" | grep identifier

# Check registered agents (should show tv.plex.agents.* after ~9s)
kubectl exec -n media <pod> -- curl -s "http://localhost:32400/media/providers?X-Plex-Token=$TOKEN" | grep -oP 'identifier="[^"]*"' | sort -u

# Force Flux reconcile
flux reconcile source git cluster -n flux-system && flux reconcile helmrelease plex -n media
```

## Cache Files (if stale auth issues)
Located at `/config/Library/Application Support/Plex Media Server/Cache/`:
- `Flags.dat`, `CloudUsersF.dat`, `CloudAccountV2.dat`, `CloudUsersSubscriptionsV2.dat`, `CloudUsersServices.dat`, `CloudUsersV2.dat`
- Clearing these forces fresh fetch from plex.tv on next startup (scale down pod first)
