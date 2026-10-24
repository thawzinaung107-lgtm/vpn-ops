# VPN Ops — Amnezia Panel + DO Control + Failover Toolkit

Operator stack built on top of the [PRVTPRO Amnezia-Web-Panel](https://github.com/PRVTPRO/Amnezia-Web-Panel):
a DigitalOcean provisioning module, a Cloudflare DNS failover layer, per-node config backups,
and a Telegram monitor — all driven from the panel VPS.

## Components

| Path | What it does |
|---|---|
| `do-panel/app.py` | FastAPI web UI at `https://share.<domain>/do` — manage DO API tokens, create/destroy droplets, full VPN bootstrap, activity log. Auth reuses the panel admin password. |
| `failover/do_provision.py` | CLI one-shot: create droplet + firewall + docker + AWG + panel registration |
| `failover/bootstrap_node.py` | Worker called by the UI and CLI: installs Docker, pins host key, adds node to panel, installs AWG |
| `failover/failover_user.py` | Flip one user's `u-<name>.<domain>` A record to a new node IP via Cloudflare API |
| `failover/failover.py` | Low-level Cloudflare A-record upsert/status |
| `failover/backup_nodes.sh` | Snapshot every node's `/opt/amnezia/awg/` (server keys + clientsTable) to the panel box |
| `failover/monitor.py` | Cron monitor: per-node online users + traffic; Telegram alerts (down / 40-user warning / 50-user capacity / recovery); daily digest |

## Install on the panel VPS

```bash
sudo ./install.sh        # copies files, writes systemd unit + crons, prompts for secrets
```

Secrets live in `/etc/environment` (chmod 600): `DO_API_TOKEN`, `CF_API_TOKEN`, `CF_ZONE_ID`,
`TG_TOKEN`, `TG_CHAT`, `PANEL_PASS`. The panel itself (PRVTPRO image) runs separately.

## Failover workflow

1. Node dies → `./failover/backup_nodes.sh` already has its keys in `/opt/vpn-backups/<ip>/latest.tgz`
2. Provision replacement: `python3 do_provision.py node-2` (or use the web UI)
3. Restore keys on the new node:
   `scp backups/<old-ip>/latest.tgz root@NEW:/tmp/ && ssh root@NEW "cd /tmp && tar xzf latest.tgz && docker cp awg-snap/. amnezia-awg:/opt/amnezia/awg/ && docker restart amnezia-awg"`
4. Flip users: `python3 failover_user.py david <NEW_IP>`
5. Users toggle reconnect — same `vpn://` link, zero re-import

Verified end-to-end: server keypair preserved → client reconnects to new IP with the original link.
