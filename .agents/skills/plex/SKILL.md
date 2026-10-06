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

## Known Issue: play_queue_items INT32 Overflow (RESOLVED 2026-02-23)

### Root Cause
Plex's C++ code uses `int32_t` for `play_queue_items.id` internally. After enough play queue activity, the SQLite autoincrement ID exceeds INT32_MAX (2,147,483,647), causing `std::exception` on every `POST /playQueues` → HTTP 500.

**Symptom**: Every `POST /playQueues` returns 500 with `Got exception from request handler: std::exception` in the server log, even with valid metadata items. GET requests and library browsing work fine.

**Secondary symptom**: `download_queue_items` entries stuck in `status=5` ("wrong state") cause `BackgroundProcessingQueue.cpp:64` to crash on startup — but this is separate from the playQueue 500 and does NOT block playback once the INT32 overflow is fixed.

### Fix
```bash
POD=$(kubectl get pod -n media -l app.kubernetes.io/name=plex -o jsonpath='{.items[0].metadata.name}')

# Check if IDs exceed INT32_MAX (2147483647)
kubectl exec -n media $POD -- "/usr/lib/plexmediaserver/Plex SQLite" \
  "/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db" \
  "SELECT COUNT(*), MIN(id), MAX(id) FROM play_queue_items;"

# If MAX(id) > 2147483647, clear play queue tables (session data only — safe to delete)
kubectl exec -n media $POD -- "/usr/lib/plexmediaserver/Plex SQLite" \
  "/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db" \
  "BEGIN; DELETE FROM play_queue_items; DELETE FROM play_queues; DELETE FROM play_queue_generators; DELETE FROM sqlite_sequence WHERE name IN ('play_queue_items', 'play_queues', 'play_queue_generators'); COMMIT;"
```

No pod restart required. Verify with:
```bash
kubectl exec -n media $POD -- curl -s -w "\nHTTP:%{http_code}" -X POST \
  "http://localhost:32400/playQueues?type=video&includeChapters=1&continuous=1&repeat=0&shuffle=0&uri=server%3A%2F%2Fd314a2f9c39c657c0c03b262d36a0395bf90376f%2Fcom.plexapp.plugins.library%2Flibrary%2Fmetadata%2F1&key=%2Flibrary%2Fmetadata%2F1&X-Plex-Token=$TOKEN" \
  -H "X-Plex-Client-Identifier: test-client-123"
# Should return HTTP:200
```

### Fix for download_queue_items stuck in status=5
```bash
# Delete stuck items (BPQ will skip cleanly on restart)
kubectl exec -n media $POD -- "/usr/lib/plexmediaserver/Plex SQLite" \
  "/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db" \
  "PRAGMA wal_checkpoint(TRUNCATE); DELETE FROM download_queue_items WHERE status = 5; SELECT changes();"
```

## Plex Bundled SQLite
The `sqlite3` binary is **not** installed in the container, but Plex ships its own:
```bash
"/usr/lib/plexmediaserver/Plex SQLite" "<path-to-db>" "<SQL statement>"
```
The main library database is at:
```
/config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db
```

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
