#!/usr/bin/env python3
"""Bootstrap a fresh droplet: docker + AWG install + panel add. Called by do_provision.py and the DO web UI."""
import sys, time, subprocess, requests
ip=sys.argv[1]
KEY='/root/.ssh/vpn_node_key'
PANEL='http://127.0.0.1:5000'; PANEL_USER='admin'
import os; PANEL_PASS=os.environ.get('PANEL_PASS','')
def sh(cmd, timeout=420):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
r=sh(f'ssh -i {KEY} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@{ip} '
     '"apt-get update -qq && apt-get install -y -qq ca-certificates curl gnupg >/dev/null && '
     'install -m 0755 -d /etc/apt/keyrings && '
     'curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && '
     'echo \\"deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable\\" > /etc/apt/sources.list.d/docker.list && '
     'apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null && '
     'systemctl enable --now docker && echo DOCKER-OK"', 420)
print('docker:', 'OK' if 'DOCKER-OK' in r.stdout else r.stdout[-200:]+r.stderr[-200:])
hk=subprocess.run(['ssh-keyscan','-t','ed25519',ip],capture_output=True,text=True,timeout=30).stdout
vol=subprocess.run(['bash','-c',"docker volume ls --format '{{.Name}}' | grep amnezia_data"],capture_output=True,text=True).stdout.strip()
open(f'/var/lib/docker/volumes/{vol}/_data/ssh_known_hosts','a').write(hk if hk.endswith('\n') else hk+'\n')
subprocess.run(['docker','restart','amnezia_panel'],check=True); time.sleep(6)
s=requests.Session(); s.post(f'{PANEL}/api/auth/login',json={'username':PANEL_USER,'password':PANEL_PASS})
r=s.post(f'{PANEL}/api/servers/add',json={'name':f'node-{ip}','host':ip,'ssh_port':22,'username':'root','private_key':open(KEY).read()},timeout=90)
sid=r.json().get('server_id'); print('panel server_id:',sid)
r=s.post(f'{PANEL}/api/servers/{sid}/install',json={'protocol':'awg'},timeout=580)
print('awg install:',r.status_code)
print('BOOTSTRAP-DONE')
