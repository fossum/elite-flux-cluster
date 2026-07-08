---
name: ibeam
description: Guidelines and constraints for configuring and debugging the IBeam Interactive Brokers client in Kubernetes.
---

# IBeam Guidelines

## 2FA DOM Elements
Interactive Brokers frequently updates their authentication page DOM elements. The PyOTP 2FA handler defaults in IBeam often target outdated or hidden DOM elements (such as `twofactbase` or `xyz-field-bronze-response`), causing IBeam to silently loop on login attempts, continually reloading the auth page after encountering an internal `Select` element exception.

You MUST override the 2FA element IDs in the container `env` values to match the current visible fields for successful 2FA. For example, if the page uses `xyz-field-silver-response` for the "Mobile Authenticator App Code":
```yaml
env:
  IBEAM_TWO_FA_EL_ID: "ID@@xyz-field-silver-response"
  IBEAM_TWO_FA_INPUT_EL_ID: "ID@@xyz-field-silver-response"
```
Do not set `IBEAM_TWO_FA_SELECT_EL_ID` to an input field to avoid Selenium exceptions.

## Read-Only Filesystem
IBeam runs a headless Chrome browser internally which requires extensive write access to the filesystem (for profiles, logs, and temp files). When deploying in strict Kubernetes environments, you must set `readOnlyRootFilesystem: false` in the pod's security context.
