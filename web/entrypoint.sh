#!/bin/sh
# The fly volume mounts as root; hand it to the app user, then drop privileges.
set -e
mkdir -p /data/runs /data/claude-config
chown -R app:app /data
# one worker: the runner keeps the single active run in this process; threads serve pages
exec runuser -u app -- gunicorn --chdir /app/web --bind 0.0.0.0:8080 --workers 1 --threads 8 \
     --timeout 150 app:app
