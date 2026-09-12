---
name: gitlab
description: GitLab deployment, backup, restore, and post-restore troubleshooting guide for the elite-flux-cluster. Use this when asked about GitLab outages, restores from MinIO, toolbox backups, or GitLab-specific credential mismatches.
---

# GitLab Troubleshooting Skill — elite-flux-cluster

## Deployment Overview
- **Namespace**: `gitlab`
- **HelmRelease**: `apps/gitlab/gitlab/app/helm-release.yaml`
- **Chart**: `gitlab` — check `helm-release.yaml` for the currently pinned version (this drifts;
  was `10.2.1` / app `19.2.1` as of the PG16→PG17 + Gateway API cleanup work, see below)
- **App Kustomization**: `apps/gitlab/gitlab/app/kustomization.yaml`
- **Ingress hosts**:
  - `gitlab.thefoss.org`
  - `kas.thefoss.org`
  - `registry.thefoss.org`

## Architecture Notes
- GitLab uses **external PostgreSQL** via CloudNativePG:
  - host: `gitlab-cnpg-main-17-rw.gitlab.svc.cluster.local` (name carries the PG major version —
    check `global.psql.host` in `helm-release.yaml` for the current one, it changes on major
    version migrations; see `cnpg-gitops-recovery` skill §4 for the migration procedure)
  - credentials secret: `gitlab-cnpg-main-17-app` (CNPG auto-names this `<cluster-name>-app`)
- GitLab uses **external Redis**, not the chart-managed Redis:
  - host: `redis.infrastructure.svc.cluster.local`
  - credentials secret: `gitlab-redis-secret`
- GitLab uses **external MinIO**, not the chart-managed MinIO:
  - object storage secret: `gitlab-minio-storage`
  - toolbox backup secret: `gitlab-s3-configuration`
  - backup bucket: `gitlab-backup-storage`
  - **registry storage secret is a different format, do not reuse `gitlab-minio-storage`**: Rails'
    `global.appConfig.object_store.connection` wants the "fog" shape
    (`provider: AWS`, `region`, `aws_access_key_id`, `aws_secret_access_key`, `endpoint`,
    `path_style`). The container registry's own `registry.storage.secret`/`.key` wants a
    completely different shape — a `storage/config` file with a top-level driver block:
    ```yaml
    s3:
      accesskey: "..."
      secretkey: "..."
      region: "us-east-1"
      regionendpoint: "http://minio-api.storage.svc.cluster.local:10106"
      bucket: "gitlab-registry-storage"
      secure: false
      v4auth: true
      pathstyle: true
    ```
    Pointing the registry at the fog-format secret doesn't error at apply time — it crash-loops
    the registry pod at runtime with `configuration error: parsing config.yml: yaml: unmarshal
    errors: line N: cannot unmarshal !!map into string`. Use a dedicated secret
    (`apps/gitlab/registry-storage.secret.yaml`, e.g. `gitlab-registry-storage-driver`, key
    `config`) for the registry.
- GitLab toolbox is the restore/backup entrypoint. The toolbox image includes:
  - `/usr/local/bin/backup-utility`
  - `gitlab-backup-cli`
  - `aws`
  - `s3cmd`
  - `/etc/gitlab/.s3cfg`

## Chart Major-Version Upgrades (e.g. 9.x → 10.x)

GitLab does **not support downgrading** once a version's migrations have run against the database
— if a chart bump is reverted after its migrations executed but before the app itself came up
cleanly, the DB is left in a stuck hybrid schema state (some newer tables/columns present, others
pending) that the older app code can neither use nor cleanly roll back from. Re-attempting the
*same* upgrade forward (fixing whatever actually broke) is the only real way out — there is no
"just revert the values.yaml" escape hatch once migrations have started. `gitlab-rake
gitlab:db:schema_checker:run` and `db:migrate:status` (look for `NO FILE` entries dated recently,
not the expected old/pre-2020 ones, and for `down` rows) are how you tell whether this has
happened.

Before editing `global.appConfig`/`global.gatewayApi`/etc. in `helm-release.yaml` for a version
bump, **pull the real chart and check its actual `values.yaml` and `_checkConfig_*.tpl`
templates** rather than guessing keys from memory or docs:
```bash
helm repo add gitlab https://charts.gitlab.io/   # already added if run before
helm pull gitlab/gitlab --version <X.Y.Z> --untar --untardir /tmp/gitlab-chart-check
```
Then `helm template` locally with the real decrypted values (`sops --decrypt` the ConfigMap/inline
values, `-f` them in) before pushing — the chart's own `gitlab.checkConfig` fail-fast validation
(rendered into `NOTES.txt`, calls `fail` on problems) catches config errors for free, the same way
a real `helm upgrade` would, without touching the cluster. Two concrete traps found this way:

- **`global.appConfig.objectStorage` and `global.appConfig.consolidatedObjectStore` do not exist
  in any version of this chart.** They're silently-ignored dead keys — Helm doesn't error on
  unknown values unless a JSON schema forbids `additionalProperties`. The real key for consolidated
  object storage is `global.appConfig.object_store` (snake_case, `enabled` + `connection`). A
  previous session spent 8 commits guessing at the wrong keys; check the real chart source.
- **`global.gatewayApi.enabled: true` is chart 10.x's new default**, and disabling *only* that flag
  is not enough. Three independent gates control different pieces:
  - `global.gatewayApi.enabled` — gates the `Gateway`/`GatewayClass`/`HTTPRoute` template `if`s
  - `global.gatewayApi.installEnvoy` — gates the `envoy-gateway` **sub-chart install itself**, via
    a `condition:` on the Chart.yaml dependency, completely independent of `.enabled`
  - `global.gatewayApi.configureCertmanager` — gates whether the `certmanager-issuer` sub-chart
    renders a Gateway-mode cert-manager `Issuer`, also independent of `.enabled`

  Leaving `installEnvoy`/`configureCertmanager` on while only setting `enabled: false` leaves an
  `envoy-gateway` deployment crash-looping (holds a LoadBalancer IP) and a `gitlab-issuer` Job
  perpetually failing to apply a Gateway `Issuer` that the cert-manager admission webhook rejects
  for missing `parentRefs`. Set all three to `false` if this cluster doesn't use Gateway API
  ingress (it doesn't — see the classic-`Ingress` section below).
  - That same `gitlab-issuer` Job (not a Helm hook — a plain Job with a `ttlSecondsAfterFinished:
    1800` and an infinite internal `while ! kubectl apply; do sleep 1; done` retry loop) can also
    fail an otherwise-successful upgrade with `jobs.batch "gitlab-issuer-<hash>" not found`: if the
    overall Helm release `--wait` takes long enough, the Job's 30-minute TTL expires and Kubernetes
    garbage-collects it before Helm gets back around to polling it. See `gitops-troubleshooting`
    skill for the general Stalled/`MissingRollbackTarget` recovery pattern this produces.
- **`global.ingress.enable` is a chart-independent typo — the real key is `enabled`.** This one
  had been silently wrong (as `enable`, no `d`) since the app was first added; it never mattered
  because chart 9.x's real `global.ingress.enabled` default was `true`. Chart 10.x changed that
  default to `false`, so the typo suddenly took the site down (zero `Ingress` resources rendered)
  with no error anywhere — Helm doesn't warn on unknown keys. If ingress disappears after a chart
  bump with no explanation, suspect a silently-wrong key name before anything more exotic.

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

## Diagnosing `OpenSSL::Cipher::CipherError` — use the right decrypt method or you WILL get false positives

GitLab stores token-type encrypted columns (`runners_token_encrypted`, etc.) in **two different
formats**, and using the wrong decrypt call to check them produces `CipherError` on perfectly
valid, healthy data — indistinguishable from real corruption unless you know to check which
method you're using.

- **Legacy/static-nonce format**: bare ciphertext, no prefix. Decrypt with
  `Gitlab::CryptoHelper.aes256_gcm_decrypt(token)` (no explicit nonce — it derives the IV
  deterministically from the key itself).
- **Newer "dynamic nonce" format**: `"|" + ciphertext + <12 raw IV bytes>` — see
  `lib/authn/token_field/encryption_helper.rb`, `DYNAMIC_NONCE_IDENTIFIER = "|"`. The trailing 12
  bytes are **not** random binary, they're the first 12 *characters* of
  `Digest::SHA256.hexdigest(plaintext_token)` (i.e. printable ASCII hex chars like `34421976d2f5`)
  — packed as bytes, not the raw digest. This is intentional upstream behavior, not corruption; a
  leading `0x7c` (`|`) byte on one of these columns is the format marker, not mangled data.
  **You must decrypt these via `Authn::TokenField::EncryptionHelper.decrypt_token(token)`**, which
  parses the `|...<iv>` framing correctly before calling the underlying crypto helper. Calling the
  bare `Gitlab::CryptoHelper.aes256_gcm_decrypt(token)` on a dynamic-nonce-format token treats the
  whole `|`-prefixed+IV-suffixed string as if it were plain ciphertext and reliably throws
  `OpenSSL::Cipher::CipherError` — on a token that is completely valid and would decrypt fine
  through the real application code path.

**Before concluding any encrypted column is corrupted and clearing/regenerating it**, verify with
the real path GitLab itself uses (check the actual production backtrace for which class raised —
if it went through `token_field/encryption_helper.rb`, use `EncryptionHelper.decrypt_token`, not
the bare crypto helper), e.g.:
```ruby
# Read-only diagnostic — do NOT skip straight to clearing columns off one bad scan.
Project.where.not(runners_token_encrypted: nil).find_each do |p|
  begin
    Authn::TokenField::EncryptionHelper.decrypt_token(p.runners_token_encrypted)
  rescue => e
    puts "#{p.id} #{p.path}: #{e.class}"
  end
end
```
If you do end up clearing/regenerating a token column based on a diagnosis, keep the *old* CNPG
cluster/PVC around (Retain policy) until you've re-verified with the correct method — it's the
only way to recover the original values if the first diagnosis turns out to be a false positive
from using the wrong decrypt call.

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

## CI Runners

GitLab CI runners are a **separate HelmRelease**, not part of the GitLab chart
(`gitlab-runner.install` stays `false` in `apps/gitlab/gitlab/app/helm-release.yaml`) so their
lifecycle, RBAC and namespace are independent of the slow 60m-timeout GitLab release.

- **HelmRelease**: `apps/gitlab-runner/gitlab-runner/app/helm-release.yaml`, chart `gitlab-runner`
  pinned to `0.88.4` (appVersion 18.11.4) from the same `gitlab` HelmRepository. Keep the runner's
  minor at or below the GitLab server's — bump both together.
- **Namespaces**: manager in `gitlab-runner`, job pods in `gitlab-runner-jobs`. The split is the
  point: a compromised CI job lands in a namespace holding nothing but other job pods.
- **Parallelism** comes from `concurrent` (one transient pod per job), not from multiple runner
  registrations. A second registration would add zero capacity.
- **Token**: `apps/gitlab-runner/runner-token.secret.yaml`, keys `runner-token` (the `glrt-…`
  authentication token) and an empty `runner-registration-token` that must exist or the pod hangs
  mounting its volume. **Create the token in the GitLab UI with no expiration date** — the chart
  keeps `config.toml` on tmpfs, so a rotated token is lost on pod restart and the runner silently
  goes offline about a month later.

### Guardrails that must not be casually relaxed

| Control | Where | If you remove it |
|---|---|---|
| `rbac.rules` explicit list | helm-release.yaml | empty list makes the chart grant `*/*` on the core API group in the job namespace |
| `*_overwrite_allowed = ""` | `runners.config` TOML | a `.gitlab-ci.yml` can choose its own namespace/ServiceAccount and leave the sandbox |
| PodSecurity `baseline` on `gitlab-runner-jobs` | namespace.yaml | loses the admission-time backstop against `privileged` / `hostPath` / `hostNetwork` |
| No `[runners.kubernetes.volumes]` | `runners.config` TOML | a `host_path` entry defeats the entire namespace boundary |
| NetworkPolicy `ipBlock.except` on RFC1918 | network-policies.yaml | CI jobs regain reach to TrueNAS and the rest of the LAN |

### Runner troubleshooting

```bash
kubectl -n gitlab-runner logs deploy/gitlab-runner            # registration + job dispatch
kubectl -n gitlab-runner-jobs get pods -w                     # transient job pods
kubectl -n gitlab-runner-jobs describe resourcequota
kubectl auth can-i --list \
  --as=system:serviceaccount:gitlab-runner:gitlab-runner -n gitlab-runner-jobs
```

- `... is forbidden: User "system:serviceaccount:gitlab-runner:gitlab-runner" cannot ...` → add
  exactly that verb to `rbac.rules`; do not widen the list.
- Pod stuck mounting `projected-secrets` → a key is missing from `gitlab-runner-token`.
- Jobs cannot clone → check the NetworkPolicy allowlist and that `${NGINX_EXTERNAL_IP}` substituted.
- Rootless BuildKit failures: `newuidmap: Operation not permitted` means NoNewPrivs is on for the
  service container; `rootlesskit: operation not permitted` means AppArmor/userns is restricted on
  the node; `failed to mount overlay` needs `--oci-worker-snapshotter=native`. Never "fix" these by
  setting the jobs namespace to PodSecurity `privileged`.
