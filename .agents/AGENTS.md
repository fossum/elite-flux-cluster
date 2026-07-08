# Workspace Coding Rules

## TrueCharts Guidelines
- **Static mountPath**: Always use static, hard-coded strings for `mountPath` in `persistence` configurations. Do not use dynamic template expressions pointing to container environment variables.
- **Workload Security**: Containers requiring elevated permissions (e.g. Selenium/Xvfb) should override `securityContext` settings to run as root (`runAsUser: 0`) and disable read-only filesystem restrictions (`readOnlyRootFilesystem: false`).
