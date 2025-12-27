# GitHub Copilot Instructions

This document provides instructions for AI agents to effectively contribute to this GitOps repository.

## Architecture Overview

This is a Kubernetes GitOps repository managed by [FluxCD](https://fluxcd.io/). The cluster state is defined declaratively through YAML manifests in this repository.

- **Core Technology**: Kubernetes, FluxCD, Helm, Kustomize, and SOPS for secrets management.
- **Repository Structure**:
  - `apps/`: Contains all application definitions, organized by namespace (e.g., `apps/media`, `apps/games`). Each application is defined by a Flux `HelmRelease` and its associated `Kustomization`.
  - `charts/`: Holds custom, local Helm charts that are not from an external repository.
  - `sources/`: Defines `GitRepository` and `HelmRepository` sources for Flux to pull charts and manifests from.
  - `infrastructure/`: Contains cluster-wide infrastructure components like CRDs, operators, and core services (e.g., `cert-manager`, `cloudnative-pg`).

## Key Patterns & Conventions

### 1. Application Deployment via HelmRelease

Every application is deployed using a Flux `HelmRelease` resource.

- **Location**: `apps/<namespace>/<app-name>/app/helm-release.yaml`
- **Pattern**: A `HelmRelease` defines the chart to use (from a `HelmRepository` or a local `GitRepository` path), the target namespace, and the configuration values.
- **Example**: To deploy Plex, you would edit `apps/media/plex/app/helm-release.yaml`. Changes to the `values` section of this file configure the Plex deployment.

### 2. Configuration Management

Configuration is managed through a combination of `values` blocks within `HelmRelease` files and `ConfigMap`s referenced via `valuesFrom`.

- **`values`**: For static, release-specific configuration.
- **`valuesFrom`**: For injecting values from external `ConfigMap`s. This is used for shared settings or sensitive data that shouldn't be in the main `helm-release.yaml`.
- **Example**: In `apps/games/ark-scorched/app/helm-release.yaml`, the `loadBalancerIP` is injected from a `ConfigMap` named `game-config`.

### 3. Secrets Management with SOPS

All secrets are encrypted in the Git repository using [SOPS](httpss://github.com/getsops/sops) with `age`.

- **File Naming**: Encrypted files must end with `.secret.yaml`.
- **Workflow**:
  1.  To edit a secret, you must first decrypt it. You can use the `Decrypt File` task in VS Code.
  2.  After making changes, you **must** re-encrypt the file using the `Encrypt File` task.
  3.  Never commit a decrypted secret file.
- **Key File**: The public age key is stored in `age.agekey`.

### 4. Kustomize for Resource Organization

Flux uses `Kustomization` resources to discover and apply manifests.

- **Hierarchy**: There is a top-level `kustomization.yaml` in the `apps/` directory that recursively includes the `kustomization.yaml` files in each application's subdirectory.
- **Adding New Apps**: To add a new application, you must create its directory structure and add a reference to its `kustomization.yaml` in a parent `kustomization.yaml`.

### 5. Ingress Configuration

This cluster uses **NGINX Inc's ingress controller** (`nginx/nginx-ingress`), not the community Kubernetes ingress controller.

- **Standard Ingress**: For HTTP/HTTPS applications, use standard `Ingress` resources with `ingressClassName: external` (or `internal`).
- **HTTPS Backends**: For applications that use HTTPS backends (like Proxmox), you **must** use the `VirtualServer` CRD instead of standard `Ingress` resources.
  - NGINX Inc's ingress controller does not properly support HTTPS backends with standard Ingress resources.
  - Use `VirtualServer` with `tls.enable: true` in the upstream configuration.
  - Example: See `apps/web-services/proxmox/app/virtualserver.yaml`
- **TLS Certificates**: Use cert-manager with `Certificate` resources to provision Let's Encrypt certificates.
  - Production issuer: `thefoss-le-prod`
  - Staging issuer: `thefoss-le-stage` (for testing to avoid rate limits)
  - Let's Encrypt has a rate limit of 5 certificates per exact domain set per week.

## Developer Workflow

1.  **Modify YAML**: Make changes to `HelmRelease` files, `ConfigMap`s, or other Kubernetes manifests.
2.  **Handle Secrets**: If editing secrets, decrypt the `.secret.yaml` file, make your changes, and re-encrypt it.
3.  **Commit and Push**: Commit your changes to the Git repository.
4.  **Reconcile**: Flux will automatically detect the changes and apply them to the cluster. You can force an immediate reconciliation with the command:
    ```bash
    flux reconcile kustomization <name> --with-source
    ```
