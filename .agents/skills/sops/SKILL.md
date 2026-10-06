---
name: sops
description: SOPS secret editing, Flux decryption, and GitOps troubleshooting guide for the elite-flux-cluster. Use this when asked about encrypted secrets, live-vs-git secret state, or why Flux is not applying decrypted values.
---

# SOPS Workflow Skill — elite-flux-cluster

## When To Use This Skill
- Use this skill for:
  - editing or creating `*.secret.yaml` files
  - troubleshooting why a live Kubernetes Secret does not match the encrypted file in git
  - checking whether Flux is decrypting secrets correctly
  - recovering from SOPS or Flux reconciliation failures

## Repo Conventions
- Secrets committed to this repo must stay **encrypted** with SOPS.
- Encrypted secret manifests use the suffix:
  - `*.secret.yaml`
- Do **not** commit decrypted secret files.
- This repo relies on Flux + SOPS decryption at apply time rather than storing plaintext in git.

## Flux Decryption Path
- Top-level Flux wiring lives in:
  - `apps/flux-entry.yaml`
- That file patches child Flux `Kustomization` objects to add:
  - `spec.decryption.provider: sops`
  - `spec.postBuild.substituteFrom` for `cluster-config`
- Because of that wiring:
  - the file in git should remain encrypted
  - the **live** Kubernetes Secret should contain decrypted plaintext data

## Important Distinction: Git File vs Live Secret
- **Expected in git**:
  - `ENC[...]` SOPS ciphertext
- **Expected in the live cluster**:
  - plaintext data in the resulting Kubernetes Secret
- If the live Secret still contains `ENC[...]`, that usually means Flux never successfully completed the build/apply path. It does **not** mean the repo file should be plaintext.

## Standard Secret Editing Workflow
1. Edit the source `*.secret.yaml`.
2. Decrypt it before making changes.
3. Re-encrypt it after editing.
4. Commit and push the encrypted file.
5. Reconcile Flux and verify the live Secret contents.

## Validation Pattern
```bash
# Render repo manifests
kubectl kustomize apps

# Check the Flux Kustomization
kubectl get kustomization -n flux-system
kubectl describe kustomization -n flux-system <name>

# Check the live secret
kubectl get secret -n <namespace> <secret-name> -o yaml

# Force reconciliation when needed
flux reconcile source git cluster -n flux-system
flux reconcile kustomization <name> -n flux-system --with-source
```

## Common Failure Modes

### Malformed secret YAML
- **Symptom**: SOPS fails to encrypt or decrypt the file cleanly.
- **Cause**: invalid YAML structure, often in multiline blocks.
- **Example**: under `stringData`, a `known_hosts: |` block must have its contents indented correctly.
- **Fix**: repair the YAML first, then re-run SOPS.

### Live Secret contains ciphertext
- **Symptom**: `kubectl get secret ... -o yaml` shows values beginning with `ENC[...]`.
- **Cause**: Flux did not successfully decrypt and apply the manifest.
- **Fix**:
  - inspect the owning Flux `Kustomization`
  - fix the upstream reconcile failure
  - reconcile again so Flux recreates the Secret from the encrypted repo file

### Flux fails before decryption because of `${...}` content
- **Symptom**: Flux Kustomization reports a post-build substitution error such as:
  - `envsubst error: variable substitution failed: missing closing brace`
- **Cause**: the repo uses Flux postBuild substitution, so raw `${...}` sequences embedded in manifests can be interpreted by `envsubst`.
- **Important**: this failure can happen **before** SOPS decryption is applied to the child app path.
- **Fix patterns**:
  - avoid embedding raw `${...}` in substituted manifests
  - move risky content to a safer representation, such as base64-encoded values decoded at runtime
  - keep large shell/plugin blobs out of direct inline `${...}` form

### Secret appears broken only after pod replacement
- **Symptom**: an app worked earlier, then fails after restart or rollout.
- **Cause**: the old pod may have been using cached/authenticated runtime state, while a replacement pod must re-read the current live Secret.
- **Fix**: verify both the live Secret contents and whether the workload depends on persisted runtime state.

## Emergency Recovery Pattern
- If GitOps is blocked and the workload is down, a temporary live repair may be necessary:
  1. decrypt the repo secret locally
  2. apply the plaintext Secret directly to the cluster
  3. restore the normal GitOps path by fixing the Flux reconcile failure
  4. commit/push the repo-side fix so future reconciliations own the resource again
- Treat this as a short-term recovery step, not the final state.

## Files Most Likely To Matter
- `apps/flux-entry.yaml`
- `apps/**/ks.yaml`
- `apps/**/app/kustomization.yaml`
- `apps/**/app/*.secret.yaml`
- any `HelmRelease` or inline manifest content that contains `${...}`

## Safe Practices
- Keep secrets encrypted in git at all times.
- Verify the **live** Secret separately from the encrypted source file.
- Check Flux reconciliation status before assuming a key or secret value is wrong.
- Be careful with inline shell scripts, plugin files, or templates in manifests because `${...}` can break postBuild substitution.
