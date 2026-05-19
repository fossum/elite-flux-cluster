---
name: gitlab
description: GitLab deployment, backup, restore, and post-restore troubleshooting guide for the elite-flux-cluster. Use this when asked about GitLab outages, restores from MinIO, toolbox backups, or GitLab-specific credential mismatches.
---

# GitLab Troubleshooting Skill — elite-flux-cluster

## Deployment Overview
- **Namespace**: `gitlab`
- **HelmRelease**: `apps/gitlab/gitlab/app/helm-release.yaml`
- **Chart**: `gitlab` `8.11.2`
- **App Kustomization**: `apps/gitlab/gitlab/app/kustomization.yaml`
- **Ingress hosts**:
  - `gitlab.thefoss.org`
  - `kas.thefoss.org`
  - `registry.thefoss.org`

## Architecture Notes
- GitLab uses **external PostgreSQL** via CloudNativePG:
  - host: `gitlab-cnpg-main-rw.gitlab.svc.cluster.local`
  - credentials secret: `gitlab-cnpg-main-app`
- GitLab uses **external Redis**, not the chart-managed Redis:
  - host: `redis.infrastructure.svc.cluster.local`
  - credentials secret: `gitlab-redis-secret`
- GitLab uses **external MinIO**, not the chart-managed MinIO:
  - object storage secret: `gitlab-minio-storage`
  - toolbox backup secret: `gitlab-s3-configuration`
  - backup bucket: `gitlab-backup-storage`
- GitLab toolbox is the restore/backup entrypoint. The toolbox image includes:
  - `/usr/local/bin/backup-utility`
  - `gitlab-backup-cli`
  - `aws`
  - `s3cmd`
  - `/etc/gitlab/.s3cfg`

## Key Repo Conventions
- Keep `global.minio.enabled: false`, `redis.install: false`, and `postgresql.install: false`. This deployment is intentionally wired to external services.
- GitLab object storage and toolbox backup access are split across two secrets:
  - `gitlab-minio-storage` for object storage
  - `gitlab-s3-configuration` for toolbox backup/restore access
- Full restore work is disruptive. Scale down write-capable GitLab workloads before restore, then scale them back up afterward.

## Full Restore Workflow
1. Confirm the backup archive exists in `s3://gitlab-backup-storage/`.
2. Scale down GitLab application deployments that should not write during restore:
   - `gitlab-webservice-default`
   - `gitlab-sidekiq-all-in-1-v2`
   - `gitlab-gitlab-shell`
   - `gitlab-kas`
   - `gitlab-registry`
   - `gitlab-gitlab-exporter`
3. Keep toolbox, Gitaly, and PostgreSQL available.
4. Restore from the toolbox pod.
5. Scale workloads back up.
6. Check the web UI, migrations, Redis auth, and post-restore logs.

## Important Restore Quirks

### Backup naming mismatch
- `backup-utility --restore -t TIMESTAMP` expects a short filename like:
  - `1745772940_gitlab_backup.tar`
- The bucket may actually contain files named like:
  - `1745772940_2025_04_27_17.11.1_gitlab_backup.tar`
- If timestamp-based restore fails, restore from a local file path instead.

### `file://` restore source can clobber itself
- `backup-utility` stages local restores as `/srv/gitlab/tmp/backups/0_gitlab_backup.tar`.
- Do **not** name your downloaded source file `0_gitlab_backup.tar`, or the restore tool may overwrite its own input.

### “Latest” backup may not be a real full backup
- A backup tar can look valid but still be unusable for full restore if it is missing `db/database.sql.gz`.
- Check the tar contents before trusting a backup as a full-instance restore source.

## Common Failure Modes

### Toolbox cannot access MinIO backups
- **Symptoms**:
  - `s3cmd` or restore tooling cannot list `gitlab-backup-storage`
  - S3 auth errors from toolbox
- **Likely cause**: the MinIO user referenced by `gitlab-s3-configuration` is missing or its credentials no longer match MinIO.
- **Fix**:
  - verify the secret wiring in the HelmRelease
  - verify the live MinIO user exists with the expected access key
  - restore the missing MinIO user or rotate the secret so GitOps and MinIO agree again

### Restore wipes the current DB and then fails
- **Cause**: GitLab restore tooling can clear the target database before it discovers the selected archive is unusable.
- **Fix**:
  - validate the archive before restore
  - keep an older known-good full backup available
  - if this happens, restore from the latest archive that actually contains `db/database.sql.gz`

### Webservice or Sidekiq fails after restore with `WRONGPASS`
- **Symptoms**:
  - init containers or app pods loop after restore
  - logs show `WRONGPASS invalid username-password pair`
- **Cause**: `gitlab-redis-secret` no longer matches the real Redis password used by the external Redis StatefulSet.
- **Fix**:
  - inspect the live Redis password
  - patch `gitlab-redis-secret` to match it
  - restart the affected GitLab pods

### GitLab web UI returns 500 after restore
- **Symptom**: `/` or `/users/sign_in` returns 500, often from `RootController#index`
- **Likely cause**: restored encrypted `application_settings` values cannot be decrypted with the current Rails secret set
- **Typical exception**: `OpenSSL::Cipher::CipherError`
- **Fix pattern**:
  - run `bundle exec rake gitlab:doctor:secrets RAILS_ENV=production` from toolbox
  - if the breakage is isolated to `ApplicationSetting`, clear only the specific undecryptable encrypted fields and their IV columns
  - understand that other secret-backed data from the old instance may still need recreation unless the original Rails secrets are available

### Pending migrations after restore
- **Symptom**: pods are up but app startup remains blocked or inconsistent
- **Fix**:
  ```bash
  kubectl exec -n gitlab deploy/gitlab-toolbox -- \
    sh -lc 'cd /srv/gitlab && bundle exec rake db:migrate RAILS_ENV=production'
  ```

## Useful Commands
```bash
# Check core GitLab workloads
kubectl get pods -n gitlab
kubectl get deploy,statefulset -n gitlab

# Check HelmRelease
kubectl get helmrelease -n gitlab gitlab
kubectl describe helmrelease -n gitlab gitlab

# Inspect recent webservice failures
kubectl logs -n gitlab deploy/gitlab-webservice-default -c webservice --since=10m

# Probe the sign-in page through ingress
curl -sk -I https://gitlab.thefoss.org/users/sign_in

# Probe the service with the correct Host header
kubectl exec -n gitlab deploy/gitlab-toolbox -- \
  sh -lc 'curl -sS -I -H "Host: gitlab.thefoss.org" http://gitlab-webservice-default.gitlab.svc:8080/users/sign_in'

# Check toolbox backup access
kubectl exec -n gitlab deploy/gitlab-toolbox -- \
  sh -lc 's3cmd --config=/etc/gitlab/.s3cfg ls s3://gitlab-backup-storage/'

# Run the GitLab secrets doctor
kubectl exec -n gitlab deploy/gitlab-toolbox -- \
  sh -lc "cd /srv/gitlab && bundle exec rake gitlab:doctor:secrets RAILS_ENV=production"
```
