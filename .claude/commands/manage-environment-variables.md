Manage FileProxy production environment variables stored in AWS SSM Parameter Store under `/fileproxy/prod/`.

The AWS CLI is at `C:\Program Files\Amazon\AWSCLIV2\aws.exe`. Always prefix every `aws` invocation with `MSYS_NO_PATHCONV=1` and quote the path, e.g.:
```
MSYS_NO_PATHCONV=1 "C:\Program Files\Amazon\AWSCLIV2\aws.exe" ssm ...
```

## Known parameters

| SSM Name | Env Var | Type | Purpose |
|---|---|---|---|
| `/fileproxy/prod/fileproxy_subscriptions_enabled` | `FILEPROXY_SUBSCRIPTIONS_ENABLED` | SecureString | Feature flag: enable subscription limits |
| `/fileproxy/prod/google_client_id` | `GOOGLE_CLIENT_ID` | SecureString | Google OAuth2 — enables GDrive backend |
| `/fileproxy/prod/google_client_secret` | `GOOGLE_CLIENT_SECRET` | SecureString | Google OAuth2 secret |
| `/fileproxy/prod/dropbox_app_key` | `DROPBOX_APP_KEY` | SecureString | Dropbox OAuth2 — enables Dropbox backend |
| `/fileproxy/prod/dropbox_app_secret` | `DROPBOX_APP_SECRET` | SecureString | Dropbox OAuth2 secret |
| `/fileproxy/prod/fileproxy_vault_master_key` | `FILEPROXY_VAULT_MASTER_KEY` | SecureString | 32-byte AES envelope encryption key (base64url) |
| `/fileproxy/prod/django_secret_key` | `DJANGO_SECRET_KEY` | SecureString | Django secret key |
| `/fileproxy/prod/db_host` | `DB_HOST` | String | PostgreSQL host |
| `/fileproxy/prod/db_name` | `DB_NAME` | String | PostgreSQL database name |
| `/fileproxy/prod/db_user` | `DB_USER` | String | PostgreSQL user |
| `/fileproxy/prod/db_password` | `DB_PASSWORD` | SecureString | PostgreSQL password |
| `/fileproxy/prod/static_url` | `STATIC_URL` | String | Static files URL (CloudFront/S3) |

## Workflow

When the user runs this command:

1. **Enumerate**: Fetch all current values using `get-parameters-by-path --with-decryption` and display them in a table. Mask secrets (show only last 4 chars, e.g. `****xEJE`) unless the user explicitly asks to reveal a value.

2. **Set a value**: When the user specifies a parameter to update, use `ssm put-parameter --overwrite`. Use type `SecureString` unless the parameter is known to be a plain `String` (see table above).

3. **Instance refresh**: After setting one or more values, ask the user if they want to trigger an ASG instance refresh. If yes, run:
   ```
   MSYS_NO_PATHCONV=1 "C:\Program Files\Amazon\AWSCLIV2\aws.exe" autoscaling start-instance-refresh \
     --auto-scaling-group-name fileproxy-prod-asg \
     --region us-east-1 \
     --preferences '{"MinHealthyPercentage":100,"InstanceWarmup":120}'
   ```
   If a refresh is already in progress (`InstanceRefreshInProgress` error), inform the user that the new values will be picked up by the current refresh.

Always use `--region us-east-1`.
