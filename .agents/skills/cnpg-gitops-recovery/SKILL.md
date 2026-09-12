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
