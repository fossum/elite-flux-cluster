---
name: nextcloud-gitops-recovery
description: Guidelines and troubleshooting steps for recovering Nextcloud deployments, handling TOTP lockouts, resolving config.php secret mismatches, and restoring deleted user data.
---

# Nextcloud GitOps & Recovery Operations

This skill documents procedures for debugging Nextcloud Helm deployments, recovering access after database migrations, and restoring user data.

---

## 1. Secrets and `config.php` Regeneration

When deploying Nextcloud via the official Helm chart or TrueCharts, core cryptographic secrets (`passwordsalt`, `secret`) are stored in `/var/www/html/config/config.php` and managed by the container's init scripts.

- **Missing Secrets**: If you migrate Nextcloud to a new deployment/PVC without preserving the original `config.php`, Nextcloud will randomly generate a new `passwordsalt` and `secret` on its first boot.
- **Consequences**: Losing the original `secret` and `passwordsalt` prevents Nextcloud from decrypting:
  - App passwords
  - Two-Factor Authentication (TOTP) secrets (`twofactor_totp`)
  - External storage credentials

If this happens, users attempting to log in will encounter a **500 Internal Server Error** when Nextcloud tries to challenge them for TOTP, as it cannot decrypt their TOTP seed.

---

## 2. Resolving TOTP 500 Internal Server Errors (Lockout Recovery)

If a user gets a 500 Internal Server Error immediately after entering their username and password, it is often due to a broken TOTP configuration (e.g. lost cryptographic secrets). 

### Symptom
The `nextcloud.log` will contain:
`hash_hkdf(): Argument #2 ($key) cannot be empty in file '/var/www/html/lib/private/Security/Crypto.php'`

### Resolution
Disable the TOTP app for the affected user via the `occ` command to allow them to log in without 2FA and re-enroll:

```bash
kubectl exec -it -n nextcloud deploy/<nextcloud-deployment> -- su -s /bin/bash www-data -c "php occ twofactor:disable <username> totp"
```

---

## 3. Restoring Deleted Users and Data

When a user is deleted from Nextcloud, their database records are removed, and their data directory on the backend storage is renamed by appending `_bak` (e.g., `thorfoss` becomes `thorfoss_bak`).

If you need to restore a deleted user and their files:

1. **Recreate the User**:
   Create the user with a temporary password using `occ`.
   ```bash
   kubectl exec -it -n nextcloud deploy/<nextcloud-deployment> -- su -s /bin/bash www-data -c "OC_PASS=TempPassword123! php occ user:add --password-from-env <username>"
   ```

2. **Restore the Data Directory**:
   Rename their backup directory back to its original name. Do not let Nextcloud create a new empty directory first, or you will get a `File exists` error during the scan.
   ```bash
   kubectl exec -it -n nextcloud deploy/<nextcloud-deployment> -- su -s /bin/bash www-data -c "mv /var/www/html/data/<username>_bak /var/www/html/data/<username>"
   ```
   *Note: If a new empty directory was already created by Nextcloud, delete it first or move the contents of `_bak/files` into it.*

3. **Rescan User Files**:
   Run the file scanner to register the restored files in the database.
   ```bash
   kubectl exec -it -n nextcloud deploy/<nextcloud-deployment> -- su -s /bin/bash www-data -c "php occ files:scan <username>"
   ```
   *Note: If the scan fails with `Failed to open directory` on `files_trashbin`, simply delete the user's `files_trashbin` directory and run the scan again.*
