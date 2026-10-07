#!/usr/bin/env bash
# Ежедневный бэкап БД в S3-совместимое объектное хранилище.
# cron на хосте:  15 3 * * *  /opt/salon/deploy/backup.sh >> /var/log/salon-backup.log 2>&1
# Требуется aws CLI на хосте (apt install awscli).
set -euo pipefail
cd "$(dirname "$0")"
set -a; source .env; set +a

STAMP=$(date -u +%Y-%m-%dT%H%M%SZ)
FILE="/tmp/salon-${STAMP}.sql.gz"

docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-app}" -d "${POSTGRES_DB:-app}" --no-owner \
  | gzip -9 > "$FILE"

aws s3 cp "$FILE" "s3://${BACKUP_S3_BUCKET}/postgres/$(basename "$FILE")" \
  --endpoint-url "${BACKUP_S3_ENDPOINT}"
rm -f "$FILE"

# удаляем бэкапы старше BACKUP_KEEP_DAYS
CUTOFF=$(date -u -d "-${BACKUP_KEEP_DAYS:-30} days" +%Y-%m-%d)
aws s3 ls "s3://${BACKUP_S3_BUCKET}/postgres/" --endpoint-url "${BACKUP_S3_ENDPOINT}" \
  | awk '{print $4}' | while read -r name; do
    day=$(echo "$name" | sed -E 's/^salon-([0-9-]{10}).*/\1/')
    if [[ "$day" < "$CUTOFF" ]]; then
      aws s3 rm "s3://${BACKUP_S3_BUCKET}/postgres/$name" --endpoint-url "${BACKUP_S3_ENDPOINT}"
    fi
  done
echo "backup ok: $STAMP"
