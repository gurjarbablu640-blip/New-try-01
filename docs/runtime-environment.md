# Runtime Environment

The repository-root `.env` file is the authoritative runtime environment for Docker Compose and the backend settings loader. Process environment variables take precedence over values in that file.

Do not add new runtime values to `backend/.env`. Treat any existing file there as legacy local material until its secrets can be rotated or migrated deliberately; the application does not load it automatically.

Hive remains zero-overage by default through `HIVE_ALLOW_PAID_OVERAGE=false`. Use `HIVE_ACCOUNT_MODE=PROMO_CREDIT` only after confirming the account is using promotional credit, and never commit a real API key.
