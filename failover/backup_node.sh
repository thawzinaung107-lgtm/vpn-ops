#!/bin/bash
# Backup a node's Amnezia config to the panel box.
# Usage: backup_node.sh <server_ip> <tag>
# Restores: docker stop -> tar /opt/amnezia + docker container env -> base64 to stdout, save to file.
set -e
IP=$1; TAG=${2:-$(date +%Y%m%d-%H%M)}
DST=/opt/vpn-backups/$IP
mkdir -p $DST
echo "== backing up $IP -> $DST"
# snapshot config dir + container definition
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@$IP "
  set -e
  # dump everything the node needs to be identical on a fresh box
  tar czf - -C / opt/amnezia 2>/dev/null || true
  echo '---DOCKER-META---'
  docker inspect amnezia-awg --format '{{json .Config.Env}} {{json .HostConfig.PortBindings}}' 2>/dev/null || true
" > $DST/amnezia-$TAG.tar.gz
ls -la $DST/
echo "backup done -> $DST/amnezia-$TAG.tar.gz"
