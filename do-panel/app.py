#!/usr/bin/env python3
"""DO control module for the VPN panel — mounted at share.vpnbydavid.site/do/"""
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import os, json, time, requests, subprocess, threading

DATA_FILE="/opt/do-panel/do_state.json"
CF_TOKEN=os.environ.get("CF_API_TOKEN",""); ZID=os.environ.get("CF_ZONE_ID","")
PANEL="http://127.0.0.1:5000"
app=FastAPI()

def load(): return json.load(open(DATA_FILE)) if os.path.exists(DATA_FILE) else {"tokens":[],"log":[]}
def save(d): json.dump(d,open(DATA_FILE,"w"))

def log(msg):
    d=load(); d["log"].insert(0,f"{time.strftime('%H:%M:%S')} {msg}"); d["log"]=d["log"][:50]; save(d)

def do_req(tok, method, path, body=None):
    return requests.request(method, f"https://api.digitalocean.com/v2/{path}",
        headers={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}, json=body, timeout=30).json()

PAGE = """<!DOCTYPE html><html><head><title>DO Control — VPN Panel</title>
<style>
body{font-family:system-ui;background:#0f1220;color:#e8eaf6;margin:0;padding:24px}
h1{font-size:1.4em} h2{font-size:1.1em;margin-top:28px}
.card{background:#1a1f36;border-radius:12px;padding:18px;margin-bottom:16px;max-width:900px}
input,select,button{background:#232a4d;color:#fff;border:1px solid #3a4374;border-radius:8px;padding:8px 12px;margin:4px 0}
button{cursor:pointer;background:#5c6bc0} button:hover{background:#7986cb}
button.red{background:#c0392b}
table{width:100%%;border-collapse:collapse} td,th{padding:6px 10px;text-align:left;border-bottom:1px solid #2a3055}
.ok{color:#81c784}.err{color:#e57373}.muted{color:#9fa8da;font-size:.85em}
#log{max-height:220px;overflow-y:auto;font-family:monospace;font-size:.8em;color:#b0bec5}
</style></head><body>
<h1>🖥️ DigitalOcean Control</h1>
<div class="card"><h2>🔑 API Keys</h2>
<table><tr><th>Label</th><th>Token</th><th>Account</th><th>Limit</th><th></th></tr>
__TOKEN_ROWS__</table>
<form method="post" action="/do/tokens">
<input name="label" placeholder="label (e.g. main)" required style="width:120px">
<input name="token" placeholder="dop_v1_..." required style="width:340px">
<button>Add Key</button></form></div>
<div class="card"><h2>🚀 Create Droplet + VPN node</h2>
<form method="post" action="/do/create">
<select name="token">__TOKEN_OPTS__</select>
<input name="name" placeholder="node-name" required style="width:140px">
<select name="region">__REGION_OPTS__</select>
<select name="size">__SIZE_OPTS__</select>
<label style="font-size:.85em"><input type="checkbox" name="bootstrap" checked> install Docker+AWG+add to panel</label>
<button>Create</button></form>
<div class="muted">creates droplet with vpn-node key + firewall, optional full VPN bootstrap</div></div>
<div class="card"><h2>📦 Droplets</h2>
<table><tr><th>Name</th><th>IP</th><th>Status</th><th>Region</th><th></th></tr>
__DROP_ROWS__</table></div>
<div class="card"><h2>📜 Activity</h2><div id="log">__LOG__</div></div>
</body></html>"""

@app.get("/do")
@app.get("/do/")
def home(request: Request):
    if request.cookies.get("doauth")!="1": return RedirectResponse("/do/login")
    state=load()
    trows=""; topts=""
    for t in state["tokens"]:
        acct=t.get("account") or "—"
        trows+=f"<tr><td>{t['label']}</td><td class='muted'>{t['token'][:12]}...</td><td>{acct}</td><td>{t.get('limit','—')}</td><td><form method=post action='/do/tokens/del' style='display:inline'><input type=hidden name=label value='{t['label']}'><button class=red>del</button></form></td></tr>"
        topts+=f"<option>{t['label']}</option>"
    drows=""
    for t in state["tokens"]:
        r=do_req(t["token"],"GET","droplets")
        for d in r.get("droplets",[]):
            ip=next((n["ip_address"] for n in d["networks"]["v4"] if n["type"]=="public"),"?")
            drows+=f"<tr><td>{d['name']}</td><td><code>{ip}</code></td><td class=ok>{d['status']}</td><td>{d['region']['slug']}</td><td><form method=post action='/do/destroy' style='display:inline'><input type=hidden name=token value='{t['label']}'><input type=hidden name=did value='{d['id']}'><button class=red>destroy</button></form></td></tr>"
    regions=do_req(state["tokens"][0]["token"],"GET","regions")["regions"] if state["tokens"] else []
    ropts="".join(f"<option>{r['slug']}</option>" for r in regions if r["available"])
    sopts="".join(f"<option>{s['slug']}</option>" for s in do_req(state["tokens"][0]["token"],"GET","sizes")["sizes"] if state["tokens"] and s["available"] and s["slug"].startswith(("s-1vcpu","s-2vcpu")))
    return HTMLResponse(PAGE.replace("__TOKEN_ROWS__",trows).replace("__TOKEN_OPTS__",topts).replace("__REGION_OPTS__",ropts).replace("__SIZE_OPTS__",sopts).replace("__DROP_ROWS__",drows).replace("__LOG__","<br>".join(state["log"])))

@app.get("/do/login")
def login(): return HTMLResponse("<body style='background:#0f1220;color:#fff;font-family:system-ui;display:grid;place-items:center;min-height:100vh'><form method=post action='/do/login' class='card'><h2>Panel Admin Login</h2><input name=pw type=password placeholder='panel password'><button>Login</button></form></body>")

@app.post("/do/login")
def do_login(request: Request, pw: str = Form("")):
    import requests as rq
    if rq.post(f"{PANEL}/api/auth/login", json={"username":"admin","password":pw}, timeout=10).status_code==200:
        resp=RedirectResponse("/do",303); resp.set_cookie("doauth","1",httponly=True); return resp
    return RedirectResponse("/do/login",303)

@app.post("/do/tokens")
async def add_token(request: Request, label: str = Form(""), token: str = Form("")):
    if request.cookies.get("doauth")!="1": return RedirectResponse("/do/login",303)
    d=load()
    acct=do_req(token,"GET","account").get("account",{})
    d["tokens"]=[t for t in d["tokens"] if t["label"]!=label]
    d["tokens"].append({"label":label,"token":token,"account":acct.get("email","?"),"limit":acct.get("droplet_limit","?")})
    save(d); log(f"token '{label}' added ({acct.get('email','?')})")
    return RedirectResponse("/do",303)

@app.post("/do/tokens/del")
async def del_token(request: Request, label: str = Form("")):
    d=load(); d["tokens"]=[t for t in d["tokens"] if t["label"]!=label]; save(d)
    return RedirectResponse("/do",303)

@app.post("/do/create")
async def create(request: Request, token: str=Form(""), name: str=Form(""), region: str=Form("sgp1"), size: str=Form("s-2vcpu-4gb"), bootstrap: str=Form("")):
    if request.cookies.get("doauth")!="1": return RedirectResponse("/do/login",303)
    tok=next((t["token"] for t in load()["tokens"] if t["label"]==token), None)
    if not tok: return RedirectResponse("/do",303)
    def work():
        try:
            key=do_req(tok,"GET","account/keys").get("ssh_keys",[])
            kid=key[0]["id"] if key else None
            body={"name":name,"region":region,"size":size,"image":"ubuntu-24-04-x64","wait":True}
            if kid: body["ssh_keys"]=[kid]
            d=do_req(tok,"POST","droplets",body)["droplet"]
            ip=next(n["ip_address"] for n in d["networks"]["v4"] if n["type"]=="public")
            log(f"droplet {name} created: {ip}")
            fws=do_req(tok,"GET","firewalls").get("firewalls",[])
            fwid=next((f["id"] for f in fws if "vpn" in f["name"].lower() or "panel" in f["name"].lower()), None)
            if fwid: requests.post(f"https://api.digitalocean.com/v2/firewalls/{fwid}/droplets",headers={"Authorization":f"Bearer {tok}"},json={"droplet_ids":[d["id"]]},timeout=15); log(f"firewall attached")
            if bootstrap:
                env=dict(os.environ); env["DO_API_TOKEN"]=tok
                r=subprocess.run(["python3","/opt/failover/bootstrap_node.py",ip], env=env, capture_output=True, text=True, timeout=900)
                log("bootstrap: "+(r.stdout.strip()[-200:] or r.stderr.strip()[-200:]))
        except Exception as e: log(f"ERROR: {e}")
    threading.Thread(target=work,daemon=True).start()
    return RedirectResponse("/do",303)

@app.post("/do/destroy")
async def destroy(request: Request, token: str=Form(""), did: int=Form(0)):
    tok=next((t["token"] for t in load()["tokens"] if t["label"]==token), None)
    if tok: do_req(tok,"DELETE",f"droplets/{did}"); log(f"droplet {did} destroyed")
    return RedirectResponse("/do",303)
