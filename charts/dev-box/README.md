# dev-box Helm Chart

A simple development box container with:

- Non-root user (UID/GID 25000) by default
- OpenSSH server
- Python 3.13 + pip + Pipenv
- Docker CLI (mount host docker.sock to control host Docker)

The container runs `sshd` via `/usr/bin/start_server`. When running as non-root (default via securityContext), it listens on port 2222. When running as root, it listens on port 22.

## Values

```yaml
service:
  type: ClusterIP            # ClusterIP | LoadBalancer | NodePort
  loadBalancerIP: ""         # when type=LoadBalancer and using MetalLB
  sshPort: 2222              # container port and Service targetPort

persistence:
  main:
    size: 20Gi
    storageClassName: ""
    existingClaim: ""

server:
  image: dev-box:latest      # container image
```

## Security Context

This chart sets pod-level security context so processes run as non-root by default:

```yaml
template:
  spec:
    securityContext:
      runAsUser: 25000
      runAsGroup: 25000
      fsGroup: 25000
      fsGroupChangePolicy: OnRootMismatch
```
Container-level hardening:

```yaml
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: false
  capabilities:
    drop: ["ALL"]
```

If you want to use port 22, either:

- Set `service.sshPort: 22` and run as root (override pod securityContext), or
- Use a Service that exposes 22 and set `service.targetPort` to 2222 (requires editing template) while container keeps 2222.

## Environment Variables

- `DEV_PASSWORD` – optional; if running as root, set the user's password
- `AUTHORIZED_KEYS` – optional; newline-separated public keys populated into `~/.ssh/authorized_keys`
- `SSH_PORT` – override default port (2222 non-root, 22 root)

## Docker-in-Docker (docker CLI)

The image includes the Docker CLI. To control the host Docker daemon from inside the Pod, mount the host socket in your workload (e.g., extra volume/volumeMount in values or a patch):

```yaml
volumes:
  - name: docker-sock
    hostPath:
      path: /var/run/docker.sock
      type: Socket
containers:
  - name: main
    volumeMounts:
      - name: docker-sock
        mountPath: /var/run/docker.sock
```

You may also need to ensure the `docker` group ID matches the socket's group or set `fsGroup` accordingly.

## Build the Image

Build and push an image tagged as `dev-box:latest` (or override via `server.image`):

```bash
docker build -t registry.example.com/dev-box:latest -f charts/dev-box/container/Dockerfile charts/dev-box/container
docker push registry.example.com/dev-box:latest
```

Then set:

```yaml
server:
  image: registry.example.com/dev-box:latest
```

## Access

- Service type `ClusterIP` with Ingress/port-forward, or
- `LoadBalancer` for direct LAN access, or
- `NodePort` if you don’t have MetalLB.

SSH to the Pod IP or Service/LoadBalancer IP on the configured port (default 2222).
