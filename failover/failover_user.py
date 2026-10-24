#!/usr/bin/env python3
"""failover USER IP|--status -- point user's A record to new node IP.
Usage:
  failover_user.py david 178.128.111.64   # flip user 'david' to new IP
  failover_user.py david --status         # show current record
"""
import os, sys, requests
CF_TOKEN=os.environ["CF_API_TOKEN"]; ZID=os.environ.get("CF_ZONE_ID","dbb5a761d21da9e7af9dc2453f0f583b")
BASE=f"https://api.cloudflare.com/client/v4/zones/{ZID}/dns_records"
H={"Authorization":f"Bearer {CF_TOKEN}","Content-Type":"application/json"}
def find(name):
    r=requests.get(BASE,headers=H,params={"type":"A","name":name},timeout=15).json()
    return r["result"][0] if r["success"] and r["result"] else None
def main():
    sub=sys.argv[1]; arg=sys.argv[2] if len(sys.argv)>2 else "--status"
    name=f"u-{sub}.uiuiufs.site" if not sub.startswith("u-") else f"{sub}.uiuiufs.site"
    if arg=="--status":
        rec=find(name)
        print(f"{name} -> {rec['content']}" if rec else f"{name}: no record")
        return
    ip=arg; rec=find(name)
    if rec:
        r=requests.put(f"{BASE}/{rec['id']}",headers=H,json={"type":"A","name":name,"content":ip,"ttl":60,"proxied":False},timeout=15).json()
    else:
        r=requests.post(BASE,headers=H,json={"type":"A","name":name,"content":ip,"ttl":60,"proxied":False},timeout=15).json()
    print(("updated" if rec else "created"), name, "->", ip)
if __name__=="__main__": main()
