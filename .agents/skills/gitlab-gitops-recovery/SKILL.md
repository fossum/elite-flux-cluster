---
name: gitlab-gitops-recovery
description: Guidelines, storage bindings, database restoration procedures, and troubleshooting steps for GitLab running under FluxCD GitOps with CloudNative-PG, Gitaly, and MinIO.
---

# GitLab GitOps & Recovery Operations

This skill documents architectural patterns, persistent volume re-binding procedures, database restoration steps, and common error resolutions for GitLab deployed via FluxCD in this cluster.

---

## 1. Architecture Overview & Persistent Storage Mapping

GitLab is deployed in the `gitlab` namespace via FluxCD `HelmRelease` (`apps/gitlab/gitlab/app/helm-release.yaml`) and depends on three main persistent data components:

| Component | Storage Driver / Class | Resource Name | PV / Data Content |
| :--- | :--- | :--- | :--- |
| **PostgreSQL DB** | Longhorn (`longhorn`) | `gitlab-cnpg-main` (CNPG Cluster) | `gitlabhq_production` database |
| **Git Repositories** | TrueNAS NFS (`truenas-nfs-api-csi`) | `repo-data-gitlab-gitaly-0` (StatefulSet PVC) | Raw git repo directories & `@hashed` objects |
| **Object Storage** | TrueNAS iSCSI (`truenas-iscsi-api-csi`) | `minio-config` (`storage` namespace) | Backup tarballs, uploads, artifacts, LFS, registry |

---

## 2. Managing PVC & PV Re-binding (Released Volume Recovery)

> [!IMPORTANT]
> Persistent volumes in GitOps should always enforce `persistentVolumeReclaimPolicy: Retain`. This ensures underlying data volumes on TrueNAS or Longhorn remain intact in a `Released` state if a PVC or namespace is deleted or recreated by FluxCD.

When enabling or re-deploying GitLab resources via GitOps, Kubernetes may provision new blank volumes if storage claims do not explicitly bind to existing persistent volumes.

### Re-binding Existing Retained PVs to PVCs

If an existing TrueNAS volume (e.g. Gitaly `pvc-d27bcb0a...` or MinIO `pvc-52e3b8...`) becomes `Released`:

1. **Clear Stale `claimRef` on the PV**:
   ```bash
   kubectl patch pv <pv-name> -p '{"spec":{"claimRef":null}}'
   ```
   *Verify status transitions from `Released` to `Available`.*

2. **Handle Active CSI VolumeAttachments (if attached to an old node)**:
   ```bash
   kubectl get volumeattachment | grep <pv-name>
   kubectl delete volumeattachment <attachment-id>
   ```

3. **Re-create PVC specifying `volumeName`**:
   Ensure the target application deployment/statefulset is scaled down or unmounted, then apply a PVC specifying `volumeName: <pv-name>`.

---

## 3. Database Backup Restoration (MinIO to CNPG)

When restoring GitLab from an object storage backup archive (e.g., `1747288616_2025_05_14_17.11.1_gitlab_backup.tar` in `s3://gitlab-backup-storage/`):

### Ensure MinIO S3 Buckets Exist
Before restoring, ensure all required GitLab S3 directories exist on MinIO (`/data/`):
* `gitlab-backup-storage`, `gitlab-uploads-storage`, `gitlab-artifacts-storage`, `gitlab-lfs-storage`, `gitlab-packages-storage`, `gitlab-registry-storage`, `gitlab-external-diffs-storage`, `gitlab-terraform-state-storage`, `gitlab-ci-secure-files-storage`, `gitlab-dependency-proxy-storage`.

### Execution Steps
1. **Run Database & Repository Restore**:
   ```bash
   kubectl exec -n gitlab deploy/gitlab-toolbox -- backup-utility --restore -t <TIMESTAMP> --skip-restore-prompt --skip uploads --skip artifacts --skip lfs --skip packages --skip registry
   ```

2. **Run Post-Restore Database Migrations (`db:migrate`)**:
   Restoring older PostgreSQL dumps requires running Rails migrations to match the deployed chart version:
   ```bash
   kubectl exec -n gitlab deploy/gitlab-toolbox -- gitlab-rake db:migrate
   ```

---

## 4. Troubleshooting: 500 Internal Server Error & Encryption Secrets Mismatches

### Symptom
GitLab returns **500 Internal Server Error** on `/` or `/users/sign_in`, and `production.log` shows:
```text
OpenSSL::Cipher::CipherError ()
encryptor (3.0.0) lib/encryptor.rb: decrypt
vendor/gems/attr_encrypted/lib/attr_encrypted.rb: attr_decrypt
```

### Root Cause
Occurs when the restored PostgreSQL database contains fields encrypted under a previous `db_key_base` in `secrets.yml` (from `gitlab-rails-secret`). When Rails attempts to render views requiring those encrypted settings (e.g. reCAPTCHA, CI job signing keys, external auth), `attr_encrypted` fails to decrypt them.

### Resolution Steps
1. **Audit Database Secrets**:
   ```bash
   kubectl exec -n gitlab deploy/gitlab-toolbox -- gitlab-rake gitlab:doctor:secrets
   ```
2. **Clear Mismatched Encrypted Settings**:
   Run Rails runner inside the toolbox pod to clear failing encrypted columns in `application_settings`:
   ```bash
   kubectl exec -n gitlab deploy/gitlab-toolbox -- gitlab-rails runner "s = ApplicationSetting.last; ['encrypted_ci_job_token_signing_key', 'encrypted_customers_dot_jwt_signing_key', 'encrypted_content_validation_api_key', 'encrypted_recaptcha_private_key', 'encrypted_recaptcha_site_key', 'encrypted_dingtalk_corpid', 'encrypted_dingtalk_app_key', 'encrypted_dingtalk_app_secret', 'encrypted_feishu_app_key', 'encrypted_feishu_app_secret'].each { |col| s.update_column(col, nil); s.update_column(col + '_iv', nil) rescue nil }"
   ```
3. **Restart Webservice & Sidekiq Deployments**:
   ```bash
   kubectl rollout restart deploy/gitlab-webservice-default deploy/gitlab-sidekiq-all-in-1-v2 -n gitlab
   ```
