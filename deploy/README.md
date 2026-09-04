# Deployment templates

These files are public examples. They intentionally contain no production domain,
host address, account name, credential, or existing server path.

1. Create a dedicated `weeknote` system account and install the repository at
   `/opt/weeknote`.
2. Copy `backend/.env.example` to `/etc/weeknote.env`, set permissions to `0600`,
   and fill in the API credentials plus these production values:

       APP_ENV=production
       APP_SECRET_FILE=/etc/weeknote.secret
       APP_PUBLIC_ORIGIN=https://example.com
       APP_COOKIE_PATH=/ask
       APP_DB_PATH=/var/lib/weeknote/data.db
       ALLOWED_HOSTS=example.com

3. Generate `/etc/weeknote.secret` with a cryptographically secure random value,
   owned by the service account and readable only by it.
4. Copy `weeknote.service.example` to the systemd unit directory, adjust paths if
   needed, then enable and start the service.
5. Copy `nginx-weeknote.example.conf` into the Nginx HTTP configuration, replace
   `example.com` and its certificate paths, validate with `nginx -t`, and reload.

Never commit the populated environment file, application secret, SQLite database,
TLS private keys, or a copy of a production server configuration.
