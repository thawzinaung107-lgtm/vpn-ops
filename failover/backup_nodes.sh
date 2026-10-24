#!/bin/bash
# Snapshot every AWG node's container-side config dir (/opt/amnezia/awg) into
# the panel box for failover restores.
set -e
BACKUP_ROOT=/opt/vpn-backups
mkdir -p "$BACKUP_ROOT"
export SSHPASS="${NODE_PASSWORD:?Set NODE_PASSWORD for password SSH to nodes}"

for host in $(python3 -c "
import json
d=json.load(open('/var/lib/docker/volumes/$(docker volume ls --format '{{.Name}}' | grep amnezia_data)/_data/data.json'))
for s in d.get('servers',[]):
    h=s.get('host')
    if h and h!='64.118.136.137': print(h)
"); do
    dest="$BACKUP_ROOT/$host"
    mkdir -p "$dest"
    ts=$(date +%Y%m%d-%H%M%S)
    sshpass -p "$NODE_PASSWORD" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 root@"$host" \
      "docker cp amnezia-awg:/opt/amnezia/awg /tmp/awg-snap && tar czf - -C /tmp awg-snap && rm -rf /tmp/awg-snap" \
      > "$dest/awg-$ts.tgz" 2>/dev/null || echo "WARN: backup failed for $host"
    ln -sf "awg-$ts.tgz" "$dest/latest.tgz"
    # prune old backups, keep last 10
    ls -t "$dest"/awg-*.tgz | tail -n +11 | xargs -r rm -f
done
echo "backup complete: $(ls -t $BACKUP_ROOT/*/latest.tgz 2>/dev/null | wc -l) nodes"
