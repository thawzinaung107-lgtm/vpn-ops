#!/usr/bin/env python3
"""DO droplet provisioning + VPN bootstrap.
Usage: do_provision.py <name> [region] [size]
  Defaults: region=sgp1 size=s-2vcpu-4gb
Creates droplet with vpn-panel-node SSH key + vpn-firewall, waits for SSH,
installs docker, pins host key, adds to panel, installs AWG.
"""
import os, sys, time, json, requests, subprocess

DO_TOKEN=os.environ["DO_API_TOKEN"]
DO_H={"Authorization":f"Bearer {DO_TOKEN}","Content-Type":"application/json"}
PANEL="http://127.0.0.1:5000"; PANEL_USER="admin"; PANEL_PASS=os.environ["PANEL_PASS"]
SSH_KEY_ID="60318545"  # vpn-panel-node
FIREWALL="new-panel-wall"

def do(method, path, body=None):
    r=requests.request(method, f"https://api.digitalocean.com/v2/{path}", headers=DO_H, json=body, timeout=30)
    r.raise_for_status(); return r.json()

def create(name, region="sgp1", size="s-2vcpu-4gb"):
    d=do("POST","droplets",{"name":name,"region":region,"size":size,"image":"ubuntu-24-04-x64",
        "ssh_keys":[int(SSH_KEY_ID)],"tags":["vpn-node"],"wait":True})
    droplet=d["droplet"]; ip=next(n["ip_address"] for n in droplet["networks"]["v4"] if n["type"]=="public")
    print(f"droplet {droplet['id']} up at {ip}")
    # attach firewall
    fw=do("GET","firewalls")["firewalls"]
    fwid=next((f["id"] for f in fw if f["name"]==FIREWALL), None)
    if fwid:
        requests.post(f"https://api.digitalocean.com/v2/firewalls/{fwid}/droplets",
            headers=DO_H, json={"droplet_ids":[droplet["id"]]}, timeout=15)
    return droplet["id"], ip

def wait_ssh(ip, timeout=180):
    import socket
    t0=time.time()
    while time.time()-t0 < timeout:
        try:
            s=socket.create_connection((ip,22),timeout=5); s.close(); return True
        except: time.sleep(5)
    return False

def bootstrap(ip):
    # docker
    subprocess.run(['ssh','-i','/root/.ssh/vpn_node_key','-o','StrictHostKeyChecking=no',
        '-o','UserKnownHostsFile=/dev/null',f'root@{ip}',
        'apt-get update -qq && apt-get install -y -qq ca-certificates curl gnupg >/dev/null && '
        'install -m 0755 -d /etc/apt/keyrings && '
        'curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && '
        'echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" > /etc/apt/sources.list.d/docker.list && '
        'apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null && '
        'systemctl enable --now docker'], check=True, timeout=420)
    # pin hostkey + add to panel
    hk=subprocess.run(['ssh-keyscan','-t','ed25519',ip], capture_output=True, text=True, timeout=30).stdout
    vol=subprocess.run(['bash','-c',"docker volume ls --format '{{.Name}}' | grep amnezia_data"],capture_output=True,text=True).stdout.strip()
    open(f"/var/lib/docker/volumes/{vol}/_data/ssh_known_hosts","a").write(hk)
    subprocess.run(["docker","restart","amnezia_panel"], check=True); time.sleep(6)
    s=requests.Session(); s.post(f"{PANEL}/api/auth/login", json={"username":PANEL_USER,"password":PANEL_PASS})
    r=s.post(f"{PANEL}/api/servers/add", json={"name":f"node-{ip}","host":ip,"ssh_port":22,"username":"root","private_key":open('/root/.ssh/vpn_node_key').read()}, timeout=90)
    sid=r.json().get("server_id"); print("panel server_id:", sid)
    r=s.post(f"{PANEL}/api/servers/{sid}/install", json={"protocol":"awg"}, timeout=580)
    print("awg install:", r.status_code)
    return sid

if __name__=="__main__":
    name=sys.argv[1]; region=sys.argv[2] if len(sys.argv)>2 else "sgp1"; size=sys.argv[3] if len(sys.argv)>3 else "s-2vcpu-4gb"
    did, ip = create(name, region, size)
    wait_ssh(ip) or sys.exit("ssh timeout")
    bootstrap(ip)
    print(f"READY: {name} {ip} (droplet {did})")
