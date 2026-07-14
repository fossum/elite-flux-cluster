# Generic NPM Container Image

This is a generic Docker image designed for running Node.js / NPM applications. It is tailored for home-lab deployments (e.g., Kubernetes with persistent volumes or NFS mounts) where application source code is mounted directly into the container.

## Features

- **Automated Git Pull at Startup**: If the application directory `/app` is a Git clone, the container can automatically pull the latest changes at runtime.
- **Smart Dependency Management**: Runs `npm install` only when necessary:
  - If `node_modules` is missing.
  - If the indicator file `/app/.install-done` is missing.
  - If `package.json` has been updated (its timestamp is newer than `/app/.install-done`).
- **Flexible Default Scripting**: Dynamically runs `npm run dev`, `npm start`, or fallbacks to `node server.js` depending on scripts defined in `package.json`.

## Configuration Options

The container can be configured using the following environment variables:

| Environment Variable | Description | Default |
| -------------------- | ----------- | ------- |
| `PORT` | The port the application server will listen on. | `3000` |
| `PULL_REPO` | If set to any non-empty value, the container will run `git pull` at startup. | *Not Set* |

## Usage in Kubernetes

When deploying this image inside a Kubernetes cluster:
1. Mount your application volume (or PVC) at `/app`.
2. Configure liveness, readiness, and startup probes (ensure the `startup` probe timeout is long enough to cover `npm install` on the initial boot).

### Example Kubernetes Environment Configuration
```yaml
env:
  - name: PORT
    value: "3000"
  - name: PULL_REPO
    value: "true"
```

## How to Build

Build and tag the docker image locally using:

```bash
docker build -t fossum/generic-npm:latest images/generic-npm/
```
