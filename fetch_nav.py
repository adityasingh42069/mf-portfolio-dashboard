"""Monthly NAV history (10y window) per scheme from Pulse; returns are computed locally from these. Cached in raw/nav.json."""
import json, os, time, urllib.request, concurrent.futures as cf
P="https://pulsedb.pulselabs.co.in/rest/api/v1/"; A=open("pulse_auth.txt").read().strip()
def post(path, body):
    err=None
    for a in range(4):
        try:
            req=urllib.request.Request(P+path, data=json.dumps(dict(body,auth=A)).encode(), headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try: return json.loads(e.read())
            except Exception: err=str(e)
        except Exception as e: err=str(e)
        time.sleep(1.5*(a+1))
    return {"error":err}
d=json.load(open("raw/screener_direct.json")); r=json.load(open("raw/screener_regular.json"))
du={x["scheme_name_unique"] for x in d}
codes=[x["scheme_code"] for x in d]+[x["scheme_code"] for x in r if x["scheme_name_unique"] not in du]
f="raw/nav.json"; res=json.load(open(f)) if os.path.exists(f) else {}
todo=[c for c in codes if c not in res]
def one(c):
    j=post("mf/nav-history", {"scheme_code":c,"from":"2016-08-01","to":"2026-10-03","frequency":"month"})
    return (j.get("data") or {}).get("nav_history") or {"_status":j.get("status") or j.get("error")}
n=0
with cf.ThreadPoolExecutor(5) as ex:
    for c,v in zip(todo, ex.map(one, todo)):
        res[c]=v; n+=1
        if n%200==0: json.dump(res,open(f,"w")); print(n,"/",len(todo),flush=True)
json.dump(res,open(f,"w")); print("NAV DONE",len(res),sum(1 for v in res.values() if "_status" not in v),flush=True)
# API trailing for cross-check (direct only, batches of 20)
tf="raw/trailing20.json"; tr={}
ch=[[x["scheme_code"] for x in d][i:i+20] for i in range(0,len(d),20)]
def t(c): return post("mf/comparision/trailing", {"scheme_codes":",".join(c),"from":"2026-09-30","ranges":"1M,3M,6M,1Y,2Y,3Y,5Y,7Y,10Y"}).get("data") or {}
with cf.ThreadPoolExecutor(4) as ex:
    for v in ex.map(t,ch): tr.update(v)
json.dump(tr,open(tf,"w")); print("TRAILING DONE",len(tr),flush=True)
