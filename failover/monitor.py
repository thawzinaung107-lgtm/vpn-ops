#!/usr/bin/env python3
"""VPN node monitor -> Telegram alerts.
Cron every 2 min. Alerts: node unreachable, peer count > threshold, daily digest 09:00 UTC.
"""
import os, sys, json, time, requests, subprocess, paramiko
from datetime import datetime, timezone

TG_TOKEN=os.environ["TG_TOKEN"]; TG_CHAT=os.environ["TG_CHAT"]
STATE="/opt/failover/monitor_state.json"
THRESH_USERS=50          # node at capacity -> suggest spinning a second droplet
WARN_USERS=40            # early heads-up before it hits 50
DATA='/var/lib/docker/volumes/'+subprocess.run(['bash','-c',"docker volume ls --format '{{.Name}}' | grep amnezia_data"],capture_output=True,text=True).stdout.strip()+'/_data/data.json'

def tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id":TG_CHAT,"text":msg,"parse_mode":"HTML"}, timeout=10)
    except Exception as e: print("tg err",e)

def node_stats(host, key='/root/.ssh/vpn_node_key', pw=None):
    c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if pw: c.connect(host,22,'root',pw,timeout=15)
    else: c.connect(host,22,'root',key_filename=key,timeout=15)
    i,o,e=c.exec_command("docker exec amnezia-awg awg show")
    out=o.read().decode(); c.close()
    peers={}; cur=None
    for line in out.splitlines():
        if line.startswith('peer:'): cur=line.split()[1]; peers[cur]={'hs':None,'rx':0,'tx':0}
        elif 'latest handshake' in line and cur: peers[cur]['hs']=line.split('handshake:')[1].strip()
        elif 'transfer' in line and cur:
            for part in line.split('transfer:')[1].split(','):
                v,u=part.strip().split()[0],part.strip().split()[1]
                m={'KiB':1e3,'MiB':1e6,'GiB':1e9}.get(u,1)
                if 'received' in part: peers[cur]['rx']=float(v)*m
                else: peers[cur]['tx']=float(v)*m
    now=time.time()
    online=sum(1 for p in peers.values() if p['hs'] and ('second' in p['hs'] or ('minute' in p['hs'] and int(p['hs'].split()[0])<3)))
    return {'peers':len(peers),'online':online,'rx':sum(p['rx'] for p in peers.values()),'tx':sum(p['tx'] for p in peers.values())}

def load_servers():
    d=json.load(open(DATA))
    return [(s['host'], s.get('password')) for s in d.get('servers',[]) if s.get('host')!='64.118.136.137']

def run():
    state=json.load(open(STATE)) if os.path.exists(STATE) else {}
    for host,pw in load_servers():
        try:
            st=node_stats(host, pw=pw); st['down']=False
            prev=state.get(host,{})
            state[host]={**st,'ts':time.time()}
            # capacity warnings — only alert once per transition
            if st['online']>=THRESH_USERS and not prev.get('full_alert'):
                tg(f"🟠 <b>{host}</b> at capacity: {st['online']}/{st['peers']} users — <b>split onto a second droplet</b>\n   → use /do create or `failover_user.py` to move half the users")
                state[host]['full_alert']=True
            elif st['online']<WARN_USERS and prev.get('full_alert'):
                state[host]['full_alert']=False
            elif st['online']>=WARN_USERS and not prev.get('warned'):
                tg(f"🟡 <b>{host}</b>: {st['online']} users online — approaching capacity ({THRESH_USERS}). Watch for the 🟠 alert.")
                state[host]['warned']=True
            if state[host].get('down_notified'): 
                tg(f"🟢 <b>{host}</b> back online ({st['online']} users)")
                state[host]['down_notified']=False
        except Exception as ex:
            was_down=state.get(host,{}).get('down',False)
            state[host]={'down':True,'ts':time.time()}
            if not was_down and not state[host].get('down_notified'):
                tg(f"🔴 <b>{host}</b> UNREACHABLE — {ex}")
                state[host]['down_notified']=True
    json.dump(state,open(STATE,'w'))

def digest():
    lines=[f"<b>VPN Daily Digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}</b>"]
    for host,pw in load_servers():
        try:
            st=node_stats(host,pw=pw)
            lines.append(f"• <code>{host}</code>: {st['online']}/{st['peers']} online · {st['rx']/1e9:.2f}GB rx / {st['tx']/1e9:.2f}GB tx")
        except: lines.append(f"• <code>{host}</code>: UNREACHABLE")
    tg("\n".join(lines))

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="digest": digest()
    else: run()
