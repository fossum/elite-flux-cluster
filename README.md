# Install

## Prerequisites

* Kubernetes Cluster: A running Kubernetes cluster (any version compatible with Flux).
* Git Repository: An empty or new Git repository (e.g., on GitHub, GitLab, Bitbucket).
* Flux CLI: Install Flux CLI.
* SOPS CLI: Install SOPS CLI.

## Steps

1. Age Key Pair: Generate an age key pair if you haven't already:

```bash
mkdir -p ~/.config/sops/age/
age-keygen -o ~/.config/sops/age/keys.txt
cat age.agekey | k create secret generic sops-age \
  --namespace flux-system \
  --from-file=age.agekey=/dev/stdin
```

1. Use [sops-secret.template.yaml] to create your sops decryption secret.

```bash
nano /tmp/sops-age-plain.yaml
```

1. Bootstrap FluxCD

```bash
flux bootstrap github
  --owner=fossum \
  --repository=elite-flux-cluster \
  --branch=main \
  --path=./apps \
  --private=false \
  --personal=true \
  --verbose \
  --encrypt-sops \
  --sops-age-key-path=~/.config/sops/age/keys.txt \
  --sops-age-key-selector=age1r0y2hakc227f26hlnuhsk6pfuy7qauqy2ak2ntwwjdpr4q6fuvuqdk8kpq
```
