#!/usr/bin/env python3
"""Cloudflare DNS failover for per-user Amnezia VPN endpoints.

Usage:
  failover.py <subdomain> <new_ip>          # point u-david.uiuiufs.site -> IP
  failover.py <subdomain> --status          # show current record
"""
import os, sys, json, requests

CF_TOKEN = os.environ["CF_API_TOKEN"]
ZONE_ID  = os.environ.get("CF_ZONE_ID", "dbb5a761d21da9e7af9dc2453f0f583b")
BASE     = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records"
H        = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}

def find_record(name):
    r = requests.get(BASE, headers=H, params={"type": "A", "name": name}, timeout=15).json()
    return r["result"][0] if r["success"] and r["result"] else None

def upsert(name, ip):
    rec = find_record(name)
    if rec:
        if rec["content"] == ip:
            print(f"unchanged: {name} -> {ip}")
            return
        r = requests.put(f"{BASE}/{rec['id']}", headers=H,
                         json={"type":"A","name":name,"content":ip,"ttl":60,"proxied":False}, timeout=15).json()
    else:
        r = requests.post(BASE, headers=H,
                          json={"type":"A","name":name,"content":ip,"ttl":60,"proxied":False}, timeout=15).json()
    if r["success"]:
        print(f"{'updated' if rec else 'created'}: {name} -> {ip}")
    else:
        print(f"ERROR: {r['errors']}"); sys.exit(1)

def status(name):
    rec = find_record(name)
    if rec:
        print(f"{name} -> {rec['content']} (ttl={rec['ttl']}, proxied={rec['proxied']})")
    else:
        print(f"{name}: no record")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(0)
    sub, arg = sys.argv[1], sys.argv[2]
    name = sub if "." in sub else f"{sub}.uiuiufs.site"
    if arg == "--status":
        status(name)
    else:
        upsert(name, arg)
