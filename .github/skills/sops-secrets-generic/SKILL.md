---
name: sops-secrets-generic
description: Generic SOPS workflow for encrypted Kubernetes secrets, safe editing, and runtime decryption validation in GitOps pipelines.
---

# SOPS Secrets Skill (Generic)

## When To Use This Skill
- A secret is encrypted in Git with SOPS.
- A controller fails while consuming secret values.
- You need to safely edit and validate secret-backed configuration.

## Goals
- Keep secrets encrypted at rest in Git.
- Ensure controllers receive valid plaintext values at runtime.
- Prevent valuesFrom parsing failures.

## Standard Workflow
1. Decrypt secret file locally.
2. Edit only intended keys.
3. Re-encrypt file.
4. Validate structure and key names.
5. Commit, push, and reconcile.

## Command Pattern
```bash
sops --decrypt <file>.secret.yaml > /tmp/secret.yaml
# edit /tmp/secret.yaml
sops --encrypt --in-place <file>.secret.yaml
```

## Runtime Validation
### 1) Confirm object kind and key paths match consumer
- If consumer expects Secret, provide Secret.
- If consumer expects ConfigMap, provide ConfigMap.
- Ensure `valuesFrom.kind`, `name`, and `valuesKey` are consistent.

### 2) Check live value availability
```bash
kubectl -n <ns> get secret <name> -o yaml
```

### 3) Controller condition checks
```bash
kubectl -n <ns> get helmrelease <name> -o yaml
```

## Failure Patterns
- Encrypted blob accidentally delivered where plaintext was expected.
- Mismatch between `valuesFrom.kind` and actual object type.
- Missing or misspelled `valuesKey`.

## Safety Rules
- Never commit decrypted secret content.
- Keep key naming stable unless consumer templates are updated.
- Validate one changed secret consumer at a time.

## Validation Checklist
- Secret decrypt/encrypt cycle succeeds.
- Live object exists in expected namespace/type.
- Consumer reports Ready without parse/value errors.
