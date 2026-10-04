"""Pull the full MF universe (Growth option, Direct + Regular) from Pulse Labs with returns, risk, metadata, analytics. Cached in raw/."""
import json, os, sys, time, urllib.request, concurrent.futures as cf
P="https://pulsedb.pulselabs.co.in/rest/api/v1/"; A=os.environ.get("PULSE_AUTH") or open("pulse_auth.txt").read().strip()
ASOF="2026-09-30"; RANGES="1M,3M,6M,1Y,2Y,3Y,5Y,7Y,10Y"
def post(path, body, tries=4):
    body=dict(body, auth=A); err=None
    for a in range(tries):
        try:
            req=urllib.request.Request(P+path, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try: return json.loads(e.read())
            except Exception: err=str(e)
        except Exception as e: err=str(e)
        time.sleep(1.5*(a+1))
    return {"error":err}
def cached(name, fn):
    f=f"raw/{name}.json"
    if os.path.exists(f): return json.load(open(f))
    v=fn(); json.dump(v, open(f,"w")); return v
def screener(plan):
    out=[]; frm=0
    while True:
        j=post("screener/search", {"plan_name":plan,"option_name":"growth","from":frm,"size":"1000"})
        d=j.get("data") or []; out+=d
        found=(j.get("info") or {}).get("found",0); frm+=len(d)
        print(plan, frm, "/", found, flush=True)
        if not d or frm>=found: break
    return out
direct=cached("screener_direct", lambda: screener("direct"))
regular=cached("screener_regular", lambda: screener("broker"))
codes_d=[x["scheme_code"] for x in direct]; codes_r=[x["scheme_code"] for x in regular]
allc=sorted(set(codes_d+codes_r))
def batched(fn, codes, n, name, workers=5):
    f=f"raw/{name}.json"; res=json.load(open(f)) if os.path.exists(f) else {}
    todo=[c for c in codes if c not in res]
    chunks=[todo[i:i+n] for i in range(0,len(todo),n)]
    done=0
    with cf.ThreadPoolExecutor(workers) as ex:
        for ch,r in zip(chunks, ex.map(fn, chunks)):
            for c in ch: res[c]=r.get(c)
            done+=1
            if done%20==0: json.dump(res,open(f,"w")); print(name, done, "/", len(chunks), flush=True)
    json.dump(res,open(f,"w")); print(name,"done",len(res),"non-null",sum(1 for v in res.values() if v), flush=True)
    return res
def trailing(ch):
    j=post("mf/comparision/trailing", {"scheme_codes":",".join(ch),"from":ASOF,"ranges":RANGES}); return j.get("data") or {}
def risk(ch):
    j=post("risk/parameters", {"scheme_codes":",".join(ch),"from":ASOF,"ranges":"3Y,5Y"}); return j.get("data") or {}
def meta(ch):
    j=post("mf/metadata", {"scheme_code":ch[0]}); return j.get("data") or {}
def ana(ch):
    j=post("mf/analytical-data", {"scheme_code":ch[0]}); return j.get("data") or {}
def annual(ch):
    j=post("mf/annual_returns", {"scheme_code":ch[0],"years":10}); return j.get("data") or {}
batched(trailing, allc, 30, "trailing")
batched(risk, codes_d, 20, "risk")
batched(meta, codes_d, 1, "meta", 6)
batched(ana, codes_d, 1, "analytical", 6)
bm=sorted({x.get("final_benchmark") for x in direct if x.get("final_benchmark")})
def bmtr(ch):
    j=post("benchmark/comparision/trailing", {"benchmarks":",".join(ch),"from":ASOF,"ranges":RANGES}); return j.get("data") or {}
batched(bmtr, bm, 10, "benchmarks")
print("ALL DONE")
