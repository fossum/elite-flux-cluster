---
name: cnpg-gitops-recovery
description: Guidelines and troubleshooting steps for inspecting CloudNative-PG (CNPG) databases, resolving WAL panic errors, and recovering Released PVCs.
---

# CloudNative-PG (CNPG) Recovery Operations

This skill documents procedures for debugging CNPG clusters, attaching standalone debug pods to existing PVCs, and resolving startup failures related to WAL corruption or major version incompatibilities.

---

## 1. Attaching Debug Pods to Released PVs

When a CNPG cluster is deleted or re-deployed with different names, its Persistent Volumes (PVs) may enter a `Released` state (assuming `persistentVolumeReclaimPolicy: Retain`). You can attach a standalone PostgreSQL debug pod to these volumes to extract data or investigate.

1. **Find the Target PV**:
   ```bash
   kubectl get pv | grep cnpg
   ```
   *Identify the old PV, e.g., `pvc-1234abcd...`.*

2. **Clear the PV ClaimRef**:
   ```bash
   kubectl patch pv <pv-name> -p '{"spec":{"claimRef":null}}'
   ```

3. **Deploy a PVC and Debug Pod**:
   Create a PVC specifying `volumeName: <pv-name>` and a Pod that mounts it without automatically starting PostgreSQL.
   
   > **CRITICAL**: The debug pod's image major version (`postgres:16`, `postgres:17`, etc.) **MUST EXACTLY MATCH** the version used to initialize the data directory. If you use the wrong major version, PostgreSQL will throw: `FATAL: database files are incompatible with server`.

   ```yaml
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: pg-debug-pvc
   spec:
     accessModes: [ReadWriteOnce]
     volumeName: <pv-name>
     resources:
       requests:
         storage: 20Gi
   ---
   apiVersion: v1
   kind: Pod
   metadata:
     name: pg-debug
   spec:
     containers:
     - name: pg
       image: postgres:16 # Ensure this matches the initialized major version!
       command: ["sleep", "infinity"]
       volumeMounts:
       - mountPath: /data
         name: data
   ```

---

## 2. Starting PostgreSQL in a Debug Pod

CNPG requires strict permissions. Before starting PostgreSQL manually, you must fix directory ownership and permissions.

1. **Fix Ownership and Permissions**:
   ```bash
   kubectl exec -it pg-debug -- chown -R postgres:postgres /data/pgdata
   kubectl exec -it pg-debug -- chmod 0700 /data/pgdata
   ```

2. **Start the Database**:
   ```bash
   kubectl exec -it pg-debug -- bash -c "su -s /bin/bash postgres -c 'pg_ctl -D /data/pgdata start'"
   ```

3. **Access the Database**:
   Since `pg_hba.conf` might restrict local access without a password, or because peer authentication might fail, you may need to explicitly specify the database and user.
   ```bash
   kubectl exec -it pg-debug -- bash -c "su -s /bin/bash postgres -c 'psql -d <database_name>'"
   ```

---

## 3. Resolving WAL Panics (`pg_wal` does not exist or `invalid checkpoint record`)

If a CNPG database was separated from its dedicated WAL volume (which happens frequently if the WAL PV is lost/deleted while the main data PV is retained), it will fail to start with one of the following errors:
- `FATAL: required WAL directory "pg_wal" does not exist`
- `PANIC: could not locate a valid checkpoint record`

### Resolution

You can force PostgreSQL to reset its Write-Ahead Log to safely start and allow you to extract a data dump.

1. **Recreate the WAL Directory**:
   If `pg_wal` is missing or points to a broken symlink (e.g. `/var/lib/postgresql/wal/pg_wal`), remove the symlink and create a physical directory:
   ```bash
   kubectl exec -it pg-debug -- rm -f /data/pgdata/pg_wal
   kubectl exec -it pg-debug -- mkdir -p /data/pgdata/pg_wal
   kubectl exec -it pg-debug -- chown postgres:postgres /data/pgdata/pg_wal
   ```

2. **Reset the WAL**:
   Use `pg_resetwal` to forcibly reset the transaction logs.
   ```bash
   kubectl exec -it pg-debug -- bash -c "su -s /bin/bash postgres -c '/usr/lib/postgresql/<MAJOR_VERSION>/bin/pg_resetwal -f /data/pgdata'"
   ```
   *Replace `<MAJOR_VERSION>` with the correct version number, e.g. `16`.*

3. **Start PostgreSQL**:
   ```bash
   kubectl exec -it pg-debug -- bash -c "su -s /bin/bash postgres -c 'pg_ctl -D /data/pgdata start'"
   ```
   The database should now start up, allowing you to run `pg_dump`.

---

## 4. Major Version Upgrades (e.g. PG16 → PG17)

CNPG (confirmed on operator `1.25.1`) has **no in-place `pg_upgrade`** — there is no
`majorVersionUpgrade` field on the `Cluster` CRD. Bumping `imageName` to a new major version on an
existing cluster does not work. The supported path is to bootstrap a **new** `Cluster` that
logically imports from the live one via `pg_dump`/`pg_restore`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: <app>-cnpg-main-17
spec:
  instances: 1
  imageName: "ghcr.io/cloudnative-pg/postgresql:17.5"   # check `crane`/GHCR tags list; no local tool for this in-cluster
  bootstrap:
    initdb:
      database: <dbname>
      owner: <owner>
      import:
        type: microservice        # single DB. `monolith` imports everything including roles.
        databases: ["<dbname>"]
        # NOTE: `roles:` is REJECTED by the admission webhook for `microservice` type
        # ("You cannot specify roles to import"). The owner role is created automatically
        # from initdb.owner instead -- don't try to import it explicitly.
        source:
          externalCluster: <old-cluster-external-name>
  externalClusters:
    - name: <old-cluster-external-name>
      connectionParameters:
        host: <old-cluster>-rw.<namespace>.svc.cluster.local
        port: "5432"
        dbname: <dbname>
        user: <owner>
        sslmode: prefer
      password:
        name: <old-cluster>-app     # CNPG's own generated app secret works fine, no superuser needed
        key: password
```

### Critical sequencing: quiesce writes *before* creating the new Cluster

The import runs **immediately and automatically** the instant the `Cluster` resource is created
(bootstrap-time only, not resumable/re-runnable). There is no way to pause it. If application
writes are still happening against the old cluster when this gets applied, anything written after
the dump starts is silently lost on cutover. Order of operations that avoids this:

1. `kubectl scale` the app's write paths (webservice, sidekiq, and anything else that writes —
   e.g. `kas`) to `0` replicas. Confirm zero active connections:
   `SELECT pid, usename, state FROM pg_stat_activity WHERE datname='<dbname>' AND pid <> pg_backend_pid();`
2. *Then* push/apply the new `Cluster` manifest and let CNPG run the import.
3. Verify row counts / table counts match between old and new (`information_schema.tables`, spot
   row counts on a few big tables) before cutting the app over.
4. Push the cutover: point the app's DB host/secret at `<new-cluster>-rw` /
   `<new-cluster>-app`, and only then scale the write paths back up.

### Gotcha: Helm won't restore your manual scale-down

If the app's chart doesn't set an explicit `replicas:` field on the Deployment (common, to coexist
with HPA), a `helm upgrade` at cutover time will **not** reset replicas back to the chart default —
it leaves whatever count is currently live on the cluster (i.e. your manual `0`). You must
`kubectl scale` the write paths back up yourself as a separate step after the cutover release
succeeds; don't assume the Helm release brought the app back.

### Continuous backup / `ScheduledBackup`

`spec.backup.barmanObjectStore` on the `Cluster` enables continuous WAL archiving + on-demand
backups, but there is **no `schedule` field on `Cluster.spec.backup`** (a stale comment/example
elsewhere in this repo claims otherwise — don't trust it). Periodic backups need a separate
`ScheduledBackup` resource:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: ScheduledBackup
metadata:
  name: <cluster>-daily
spec:
  cluster:
    name: <cluster-name>
  schedule: "0 0 2 * * *"      # 6-field cron (includes seconds)
  backupOwnerReference: self
  method: barmanObjectStore
```

The `s3Credentials` secret for `barmanObjectStore` needs its own keys (e.g. `ACCESS_KEY_ID` /
`ACCESS_SECRET_KEY`, whatever names you reference via `.key:`) — it is **not** the same secret
format as the app's own MinIO storage secret (see the `gitlab` skill for that distinction).

### Validate before touching the live cluster

`kubectl explain cluster.spec.<path> --recursive` against the live CRD (and
`kubectl apply --dry-run=server -f <file>`, which runs CNPG's real admission webhooks) catches
schema mistakes — like the `roles:` rejection above — for free, without needing docs or guessing.
Do this before pushing through GitOps, not after a failed reconcile.

---

## 5. CNPG Tiered Storage Architecture (Longhorn SSD + TrueNAS Bulk)

PostgreSQL write throughput and client transaction latency are bounded by `fsync` time on Write-Ahead Logs (`pg_wal`). Table data access, however, is heavily buffered in RAM (`shared_buffers` and Linux page cache) and requires bulk capacity.

### The Tiered Architecture Pattern
In this cluster, CNPG databases should be configured with split storage:

1. **`walStorage` -> `storageClass: longhorn` (Fast NVMe/SATA SSD Block Storage)**:
   - **Purpose**: Low-latency synchronous writes for transaction commits (`pg_wal`).
   - **Behavior**: Longhorn provides distributed block storage with sub-millisecond fsyncs, preventing NFS RPC commit stalls.
   - **Role**: Serves purely as a high-speed **transient ring buffer**. WALs should be continuously drained to MinIO S3 object storage via Barman.
2. **`storage` -> `storageClass: truenas-nfs-api-csi` (or `truenas-iscsi-csi`) (High-Capacity ZFS Storage)**:
   - **Purpose**: Bulk table, index, and heap storage (`PGDATA`).
   - **Behavior**: TrueNAS handles hundreds of GiBs to TiBs of data with snapshots, RAIDZ protection, and large capacity pools.

### Recommended Cluster Manifest Template
```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: <app>-cnpg-main
spec:
  instances: 2

  # Bulk Data Storage on TrueNAS
  storage:
    size: 50Gi                    # Size according to long-term app data needs
    storageClass: truenas-nfs-api-csi
    resizeInUseVolumes: true

  # High-Speed WAL Buffer on Longhorn SSDs
  walStorage:
    size: 30Gi                    # Minimum 30Gi for safety buffer
    storageClass: longhorn
    resizeInUseVolumes: true

  postgresql:
    parameters:
      # Sizing & rotation parameters (see Section 6)
      archive_timeout: "15min"
      wal_keep_size: "2048MB"
      max_wal_size: "10GB"
      min_wal_size: "2GB"
      checkpoint_completion_target: "0.9"
      checkpoint_timeout: "15min"

  backup:
    retentionPolicy: "14d"
    target: primary
    barmanObjectStore:
      destinationPath: "s3://<app>-postgres-backup/"
      endpointURL: "http://minio-api.storage.svc.cluster.local:10106"
      s3Credentials:
        accessKeyId:
          name: <app>-cnpg-s3-backup-creds
          key: ACCESS_KEY_ID
        secretAccessKey:
          name: <app>-cnpg-s3-backup-creds
          key: ACCESS_SECRET_KEY
```

---

## 6. Aligning PostgreSQL Parameters for Fast WAL on Limited SSDs

Because Longhorn uses local node SSDs with limited total capacity, the WAL buffer must not retain unneeded historical segments. The following parameter alignment prevents WAL volume exhaustion:

| Parameter | Recommended Value | Purpose & Interaction |
| :--- | :--- | :--- |
| `archive_timeout` | `15min` (or `10min`) | Sets maximum age before a WAL segment is archived. Avoid `5min` or less on moderate workloads: 5min forces 16MB every 5m (~4.6 GiB/day) even when idle, rapidly filling a 10–20Gi volume during backup target slowdowns. 15min produces only ~1.5 GiB/day while still meeting 15m RPO. |
| `wal_keep_size` | `2048MB` (2 GiB) | Maximum volume of WAL segments kept for streaming replicas before relying on Barman / replication slots. Never leave unbounded or larger than 20% of `walStorage.size`. |
| `max_wal_size` | `10GB` | Maximum size to let the WAL grow between automatic checkpoints. Soft limit; must remain well under `walStorage.size` (e.g. 10GB max on a 30GB volume) so checkpoints trigger before disk alerts occur. |
| `min_wal_size` | `2GB` | Prevents PostgreSQL from constantly deallocating and reallocating WAL files during normal load cycles. |
| `checkpoint_completion_target`| `0.9` | Spreads checkpoint I/O over 90% of the checkpoint duration, smoothing out disk writes to TrueNAS and Longhorn. |
| `barmanObjectStore` | Configured | Offloads archived WALs off Longhorn to MinIO S3 storage, allowing CNPG to safely delete archived local segments. |

---

## 7. Recovering from Low-Disk Space Lockout (`Detected low-disk space condition`)

### Symptoms
- Cluster status: `Not enough disk space`.
- Pod logs:
  ```json
  {"msg":"Checking for free disk space for WALs before starting PostgreSQL"}
  {"msg":"Detected low-disk space condition, avoid starting the instance"}
  ```
- Operator logs: `Insufficient disk space detected in a pod. PostgreSQL cannot proceed until the PVC group is enlarged`.

### Resolution Workflow
1. **Enlarge Manifest & Live Resources**:
   - Update `walStorage.size` to `30Gi` in the GitOps manifest (`cnpg-cluster.yaml`).
   - Patch live `Cluster` and affected PVCs:
     ```bash
     kubectl patch cluster <cluster-name> -n <namespace> --type='json' -p='[{"op":"replace","path":"/spec/walStorage/size","value":"30Gi"}]'
     kubectl patch pvc <instance>-wal -n <namespace> -p '{"spec":{"resources":{"requests":{"storage":"30Gi"}}}}'
     ```
2. **Remount & Filesystem Expansion**:
   - If the pod is in CrashLoopBackOff, delete the pod so kubelet can attach and resize the ext4 filesystem:
     ```bash
     kubectl delete pod <instance-pod> -n <namespace>
     ```

---

## 8. Resynchronizing Standby Replicas When `pg_rewind` Fails

### Symptoms
- Standby replica pod in CrashLoopBackOff.
- Pod logs:
  ```
  pg_rewind: servers diverged at WAL location ...
  pg_rewind: error: could not find previous WAL record at ...: invalid magic number 0000 in WAL segment ...
  Failed to execute pg_rewind: exit status 1
  ```
- **Cause**: Abrupt termination during low disk space leaves a trailing WAL segment with corrupted trailing/magic bytes. When another instance is promoted, `pg_rewind` cannot read through the corrupt segment.

### Resolution Workflow (Re-clone via `pg_basebackup`)
Do NOT attempt binary editing of WAL files on the replica. Force a clean re-clone:
1. Verify the primary is running: `kubectl get cluster <cluster-name> -n <namespace>`.
2. Delete the broken replica pod and both its PVCs:
   ```bash
   kubectl delete pod <broken-pod> -n <namespace>
   kubectl delete pvc <broken-pod> <broken-pod>-wal -n <namespace>
   ```
3. The CNPG operator immediately spawns a `<cluster>-<index>-join-<hash>` pod to pull a fresh `pg_basebackup` from the primary and re-establishes streaming replication.
4. Ensure the newly provisioned PVs are patched with `persistentVolumeReclaimPolicy: Retain`.
