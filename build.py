"""Build dashboard.html from raw Pulse pulls: computes returns from monthly NAVs, peer stats, AMC scores, cost and style cuts."""
import json, re, math, statistics as st, collections as C, datetime
R=lambda f: json.load(open(f"raw/{f}.json"))
direct,regular,nav,meta,ana,risk,bmk=R("screener_direct"),R("screener_regular"),R("nav"),R("meta"),R("analytical"),R("risk"),R("benchmarks")
ASOF_M=(2026,9); H=["1Y","3Y","5Y","10Y"]; HM={"1Y":12,"3Y":36,"5Y":60,"10Y":120}
CATS=["Equity","Fixed Income","Hybrid","Commodity","Global"]
SUBFIX={"Flexi Cap":"Flexi - Cap","Multi Asset":"Multi Asset Allocation","Tax Savings":"ELSS (Tax Savings)","ETF Units":"ETFs","ETF":"ETFs"}
def amc_short(n):
    n=re.sub(r"\s*-\s*SIF$","",n)
    special={"Nippon Life India":"Nippon India","LIC Mutual Fund":"LIC","Wealth Company":"The Wealth Company","The Wealth Company":"The Wealth Company"}
    s=re.split(r"\s+(Asset Management|AMC|Funds Management|Investment Manag|Money Managers|Global Asset|Capital Asset)",n)[0].strip()
    s={"Helios":"Helios","WhiteOak":"WhiteOak Capital"}.get(s,s)
    return special.get(s,s)
def months(v):
    """Month -> NAV, with unit splits (NAV falling to ~1/10 or ~1/100 in a month, common in ETFs) adjusted out."""
    ks=[k for k in sorted(v) if v[k]]; fac=1.0; m={}
    for i in range(len(ks)-1,-1,-1):
        if i<len(ks)-1:
            r=v[ks[i+1]]/v[ks[i]]
            if r<0.25: fac*=min((1/2,1/5,1/10,1/20,1/50,1/100,1/1000),key=lambda c:abs(math.log(c/r))); SPLITS.add(id(v))
        m.setdefault(ks[i][:7],v[ks[i]]*fac)
    return m
SPLITS=set()
def key(n):
    t=ASOF_M[0]*12+ASOF_M[1]-1-n; return f"{t//12}-{t%12+1:02d}"
def ret(m,n):
    a,b=m.get(key(0)),m.get(key(n))
    if not a or not b: return None
    g=a/b; return round(((g**(12/n)-1) if n>12 else g-1)*100,2)
def vol(m,n=36):
    xs=[m.get(key(i)) for i in range(n,-1,-1)]
    if any(x is None for x in xs): return None
    rr=[xs[i+1]/xs[i]-1 for i in range(n)]
    return round(st.pstdev(rr)*math.sqrt(12)*100,2)
PASSIVE=re.compile(r"\b(index|etf|nifty|sensex|bse|crisil|sdl|g-sec|gilt index|passive)\b",re.I)
du={x["scheme_name_unique"] for x in direct}
regmap={}
for x in regular: regmap.setdefault(x["scheme_name_unique"],x)
F=[]; seen=set(); sif=0
for x in direct+[y for y in regular if y["scheme_name_unique"] not in du]:
    c=x["scheme_code"]
    if c.startswith("SIF") or " - SIF" in x["amc_name"]: sif+=x in direct and 1 or 0; continue
    if c in seen or x["asset_category"] not in CATS: continue
    seen.add(c)
    v=nav.get(c) or {}
    m=months(v) if "_status" not in v else {}
    isd=x["scheme_name_unique"] in du
    etf=(not isd) and x["asset_sub_category"]=="ETF Units"
    sub=SUBFIX.get(x["asset_sub_category"],x["asset_sub_category"])
    if sub=="ETFs": sub=f"ETFs ({x['asset_category'].lower()})"
    md=meta.get(c) or {}; an=ana.get(c) or {}; rk=((risk.get(c) or {}).get("3Y") or {})
    reg=regmap.get(x["scheme_name_unique"]) if isd else None
    inc=None
    try: inc=datetime.datetime.strptime(md.get("date_of_inception",""),"%d-%b-%y").year
    except Exception: pass
    passive=bool(etf or sub.startswith("Index") or sub.startswith("ETFs") or sub in("Gilt Index Fund","Goal Based","ETF - FOF","Index","Equity - FOF") or x["asset_category"]=="Commodity" or PASSIVE.search(x["scheme_name"]))
    ter=x.get("expense_ratio") or None
    f=dict(c=c,n=x["scheme_name_unique"],a=amc_short(x["amc_name"]),cat=x["asset_category"],sub=sub,
           r={h:ret(m,n) for h,n in HM.items() if ret(m,n) is not None},
           ter=ter, terR=(reg or {}).get("expense_ratio") or None, aum=round(x["fund_size"],1) if x.get("fund_size") else None,
           st=(x.get("vr_rating") or "").count("*") or None, sh=rk.get("sharpe_ratio"), sd=vol(m), pe=(an.get("pe_ratio") or None),
           bm=x.get("benchmark") or None, fm=x.get("fund_manager") or None, rk=x.get("riskometer") or None, inc=inc)
    if etf: f["etf"]=1
    if passive: f["p"]=1
    if x.get("lock_in_period"): f["lock"]=x["lock_in_period"]
    F.append(f)
NSPLIT=len(SPLITS); print("splits",NSPLIT)
print("universe",len(F),"sif",sif,"etf",sum(1 for f in F if f.get("etf")),"passive",sum(1 for f in F if f.get("p")))
print("with returns",{h:sum(1 for f in F if h in f["r"]) for h in H})
# sanity: TER outliers (above any SEBI cap) are kept in the explorer but excluded from fee rankings
def badter(f): return bool((f["ter"] and f["ter"]>(1.5 if f.get("p") else 3.0)) or (f["terR"] and f["terR"]>(2.0 if f.get("p") else 4.5)))
for f in F: f["_bad"]=badter(f)
okter=lambda v: v is not None and v>0
NBAD=sum(f["_bad"] for f in F); print("TER outliers",NBAD,[(f["n"],f["ter"],f["terR"]) for f in F if f["_bad"]])
def stats(fs,h,name=True):
    xs=[f for f in fs if h in f["r"]]
    if not xs: return None
    v=[f["r"][h] for f in xs]; w=[(f["r"][h],f["aum"]) for f in xs if f["aum"]]
    b=max(xs,key=lambda f:f["r"][h]); wst=min(xs,key=lambda f:f["r"][h])
    o=dict(n=len(xs),avg=round(st.mean(v),2),med=round(st.median(v),2),wavg=round(sum(a*b_ for a,b_ in w)/sum(b_ for _,b_ in w),2) if w else round(st.mean(v),2),best=b["r"][h],worst=wst["r"][h])
    if name: o["bestN"]=b["n"]
    return o
def sdict(fs,**k): return {h:s for h in H if (s:=stats(fs,h,**k))}
idx={f["c"]:i for i,f in enumerate(F)}
bysub=C.defaultdict(list)
for f in F: bysub[(f["cat"],f["sub"])].append(f)
cats=[dict(cat=c,sub=s,n=len(fs),aum=round(sum(f["aum"] or 0 for f in fs)),s=sdict(fs)) for (c,s),fs in bysub.items()]
broad=[dict(cat=c,n=sum(1 for f in F if f["cat"]==c),aum=round(sum(f["aum"] or 0 for f in F if f["cat"]==c)),s=sdict([f for f in F if f["cat"]==c],name=False)) for c in CATS]
# excess vs peer average
for (c,s),fs in bysub.items():
    for h in H:
        sd_=stats(fs,h)
        if sd_ and sd_["n"]>=3:
            for f in fs:
                if h in f["r"]: f.setdefault("x",{})[h]=round(f["r"][h]-sd_["avg"],2)
# peer percentile among active funds (sub-categories with >=5 active funds on that horizon)
pctl=C.defaultdict(dict); first=C.defaultdict(set)
for (c,s),fs in bysub.items():
    for h in H:
        xs=sorted([f for f in fs if not f.get("p") and h in f["r"]],key=lambda f:f["r"][h])
        if len(xs)<5: continue
        for i,f in enumerate(xs): pctl[h][f["c"]]=i/(len(xs)-1)*100
        first[h].add(xs[-1]["c"])
AMIN={"All":5,"Equity":3,"Fixed Income":3,"Hybrid":3}
byamc=C.defaultdict(list)
for f in F: byamc[f["a"]].append(f)
def amc_score(fs,h,minn):
    xs=[f for f in fs if f["c"] in pctl[h]]
    if len(xs)<minn: return None
    p=[pctl[h][f["c"]] for f in xs]
    return dict(n=len(xs),pct=round(st.mean(p),1),beat=round(sum(1 for v in p if v>50)/len(p)*100,1),top=sum(1 for v in p if v>=75),first=sum(1 for f in xs if f["c"] in first[h]),ret=round(st.mean(f["r"][h] for f in xs),2))
amc=[]
for a,fs in byamc.items():
    s={h:v for h in H if (v:=amc_score(fs,h,AMIN["All"]))}
    amc.append(dict(a=a,n=len(fs),aum=round(sum(f["aum"] or 0 for f in fs)),s=s))
amc=[a for a in amc if a["s"]]
amcCat={}
for c in ("Equity","Fixed Income","Hybrid"):
    amcCat[c]={}
    for h in H:
        l=[dict(a=a,**v) for a,fs in byamc.items() if (v:=amc_score([f for f in fs if f["cat"]==c],h,AMIN[c]))]
        amcCat[c][h]=[dict(a=x["a"],pct=x["pct"],n=x["n"]) for x in sorted(l,key=lambda x:-x["pct"])[:5]]
best=[]
for (c,s),fs in bysub.items():
    hh={}
    for h in H:
        xs=[f for f in fs if h in f["r"]]
        if len(xs)>=2:
            b=max(xs,key=lambda f:f["r"][h]); hh[h]=dict(i=idx[b["c"]],v=b["r"][h],avg=round(st.mean(f["r"][h] for f in xs),2),n=len(xs))
    if hh: best.append(dict(cat=c,sub=s,h=hh))
cons=[idx[f["c"]] for f in F if all(pctl[h].get(f["c"],0)>=75 for h in ("3Y","5Y","10Y"))]
# ---- costs
pairs=[f for f in F if okter(f["ter"]) and okter(f["terR"]) and not f["_bad"]]
def tc(label,fs): return dict(g=label,n=len(fs),d=round(st.mean(f["ter"] for f in fs),2),r=round(st.mean(f["terR"] for f in fs),2),gap=round(st.mean(f["terR"]-f["ter"] for f in fs),2))
act_eq=lambda f: f["cat"]=="Equity" and not f.get("p")
terCat=[tc("Active equity",[f for f in pairs if act_eq(f)]),tc("Equity index funds",[f for f in pairs if f["cat"]=="Equity" and f.get("p")])]+[tc(c,[f for f in pairs if f["cat"]==c]) for c in ("Hybrid","Fixed Income","Global","Commodity")]
amcTer=[]
for a,fs in byamc.items():
    xs=[f for f in fs if act_eq(f) and okter(f["ter"]) and okter(f["terR"]) and not f["_bad"]]
    if len(xs)>=3: amcTer.append(dict(a=a,n=len(xs),d=round(st.mean(f["ter"] for f in xs),2),r=round(st.mean(f["terR"] for f in xs),2),med=round(st.median(f["aum"] or 0 for f in xs))))
mx=max(((f["terR"],f,"regular") for f in F if okter(f["terR"]) and not f["_bad"]),key=lambda t:t[0])
terCall=dict(hiR=max(amcTer,key=lambda a:a["r"]),hiD=max(amcTer,key=lambda a:a["d"]),lo=min(amcTer,key=lambda a:a["d"]),maxF=dict(n=mx[1]["n"],v=mx[0],p=mx[2]))
big=lambda f: okter(f["ter"]) and not f["_bad"] and (f["aum"] or 0)>=100 and not f.get("etf")
eff=dict(active=[idx[f["c"]] for f in F if act_eq(f) and big(f)],all=[idx[f["c"]] for f in F if f["cat"]=="Equity" and big(f)],
         hybrid=[idx[f["c"]] for f in F if f["cat"]=="Hybrid" and big(f)],debt=[idx[f["c"]] for f in F if f["cat"]=="Fixed Income" and big(f)])
# ---- styles
def named(pat,fs=None): return [f for f in (fs or F) if f["cat"]=="Equity" and f.get("p") and re.search(pat,f["n"],re.I)]
subf=lambda *s: [f for f in F if f["sub"] in s and not f.get("p")]
DIV=("Large Cap","Flexi - Cap","Multi - Cap","Large & Mid Cap","Mid Cap","Small Cap","Focused","ELSS (Tax Savings)","Value Fund","Thematic - Contra","Thematic - Dividend Yield")
rel=[]
for s in DIV:
    xs=[f for f in subf(s) if f["pe"] and f["pe"]>0]
    if len(xs)>=6:
        med=st.median(f["pe"] for f in xs)
        rel+=[(f["pe"]/med,f) for f in xs]
rel.sort(key=lambda t:t[0]); n3=len(rel)//3
peg=[("Value tilt","Cheapest third: portfolio P/E well below peers",[f for _,f in rel[:n3]]),("Blend","Middle third",[f for _,f in rel[n3:len(rel)-n3]]),("Growth tilt","Most expensive third: paying up for earnings growth",[f for _,f in rel[len(rel)-n3:]])]
peStyle=[dict(label=l,desc=d,n=len(fs),pe=round(st.mean(f["pe"] for f in fs),1),s=sdict(fs)) for l,d,fs in peg]
n50=[f for f in F if f.get("p") and not f.get("etf") and re.search(r"nifty 50 index|nifty 50 fund|nifty index|nifty 50 plan",f["n"],re.I) and f["sub"]=="Index - Large Cap"]
ST=[("Value","Buys stocks priced below the manager's estimate of worth and waits for the gap to close.","SEBI category: Value Fund",subf("Value Fund"),0),
    ("Contrarian","Buys what is out of favour: beaten-down sectors and stocks the market is avoiding. An AMC may run a value fund or a contra fund, not both.","SEBI category: Contra Fund",subf("Thematic - Contra"),0),
    ("Dividend yield","Holds companies paying high, steady dividends; usually mature and cash-rich.","SEBI category: Dividend Yield Fund",subf("Thematic - Dividend Yield"),0),
    ("Focused","Concentrates in at most 30 stocks, so each call matters more.","SEBI category: Focused Fund",subf("Focused"),0),
    ("Growth (high P/E tilt)","Pays a premium for companies growing earnings faster than the market.","Derived: top third by relative portfolio P/E",peg[2][2],0),
    ("Momentum (active)","Buys recent winners and sells laggards, by rule or by judgement.","Pulse sub-category: Thematic - Momentum",subf("Thematic - Momentum"),0),
    ("Quant","Stock selection by a model with little manager discretion.","Pulse sub-category: Thematic - Quant",subf("Thematic - Quant"),0),
    ("Momentum (factor index)","Tracks an index of the strongest recent performers.","Index funds and ETFs with Momentum in the name",named(r"momentum"),0),
    ("Value (factor index)","Tracks an index of the cheapest stocks on P/E, P/B and yield.","Index funds and ETFs with Value in the name",named(r"value"),0),
    ("Quality (factor index)","Tracks companies with high return on equity, low debt and stable earnings.","Index funds and ETFs with Quality in the name",named(r"quality"),0),
    ("Low volatility (factor index)","Tracks the least volatile stocks; aims for smaller drawdowns.","Index funds and ETFs with Low Vol in the name",named(r"low vol"),0),
    ("Alpha (factor index)","Tracks stocks with the highest risk-adjusted excess return.","Index funds and ETFs with Alpha in the name",named(r"alpha"),0),
    ("Equal weight (index)","Holds every index stock in equal size instead of by market value.","Index funds and ETFs with Equal Weight in the name",named(r"equal weight"),0),
    ("Flexi-cap funds (reference)","","",subf("Flexi - Cap"),1),
    ("Nifty 50 index funds (reference)","","",n50,1)]
styles=[dict(label=l,desc=d,src=s,n=len(fs),s=sdict(fs),**({"ref":1} if ref else {})) for l,d,s,fs,ref in ST if fs]
capStyle=[dict(label=s,n=len(subf(s)),s=sdict(subf(s),name=False),sd=round(st.mean(f["sd"] for f in subf(s) if f["sd"]),1)) for s in ("Large Cap","Large & Mid Cap","Flexi - Cap","Multi - Cap","Mid Cap","Small Cap")]
# ---- ELSS
EL=[f for f in F if f["sub"]=="ELSS (Tax Savings)"]
def prank(fs,get):
    xs=sorted([f for f in fs if get(f) is not None],key=get); return {f["c"]:i/(len(xs)-1)*100 for i,f in enumerate(xs)} if len(xs)>1 else {}
pr=[prank(EL,lambda f,h=h:f["r"].get(h)) for h in ("3Y","5Y","10Y")]+[prank(EL,lambda f:f["sh"])]
score={}
for f in EL:
    if "3Y" in f["r"] and "5Y" in f["r"]:
        v=[p[f["c"]] for p in pr if f["c"] in p]; score[f["c"]]=round(st.mean(v),1)
rk_=sorted(score,key=lambda c:-score[c]); bestE=F[idx[rk_[0]]]
el_s=sdict(EL,name=False)
def bm_ret(code):
    out={}
    for p in (bmk.get(code) or {}).get("performance",[]):
        for k,v in p.items():
            if k in H: out[k]=v
    return out
def place(f,h):
    xs=sorted([g["r"][h] for g in EL if h in g["r"]],reverse=True); return xs.index(f["r"][h])+1,len(xs)
why="Highest combined score across 3, 5 and 10-year returns and 3-year Sharpe ratio. It ranks "+", ".join(f"{place(bestE,h)[0]} of {place(bestE,h)[1]} on {h}" for h in ("3Y","5Y","10Y") if h in bestE["r"])+f", against an ELSS average of {el_s['5Y']['avg']:+.1f}% over 5 years."
elss=dict(n=len(EL),aum=round(sum(f["aum"] or 0 for f in EL)),ter=round(st.mean(f["ter"] for f in EL if okter(f["ter"])),2),avg=el_s,funds=[idx[f["c"]] for f in EL],score=score,best=idx[rk_[0]],others=[idx[c] for c in rk_[1:4]],
          top1y=idx[max((f for f in EL if "1Y" in f["r"]),key=lambda f:f["r"]["1Y"])["c"]],why=why,
          cmp=[dict(l="ELSS average",v={h:el_s[h]["avg"] for h in el_s}),dict(l="Flexi-cap average",v={h:s["avg"] for h,s in sdict(subf("Flexi - Cap"),name=False).items()}),dict(l="Large-cap average",v={h:s["avg"] for h,s in sdict(subf("Large Cap"),name=False).items()}),dict(l="Nifty 500 index",v=bm_ret("OB56"))])
# ---- headline
def topsub(h,minn=3): return max((c for c in cats if h in c["s"] and c["s"][h]["n"]>=minn and not c["sub"].startswith("ETFs")),key=lambda c:c["s"][h]["avg"])
def topamc(h): return max((a for a in amc if h in a["s"]),key=lambda a:a["s"][h]["pct"])
def topfund(h): return max((f for f in F if h in f["r"]),key=lambda f:f["r"][h])
t5,t10,a5,a10,f5,f10=topsub("5Y"),topsub("10Y"),topamc("5Y"),topamc("10Y"),topfund("5Y"),topfund("10Y")
effA=[F[i] for i in eff["active"] if "5Y" in F[i]["r"]]; e5=max(effA,key=lambda f:f["r"]["5Y"]/f["ter"])
st5=max((s for s in styles if "5Y" in s["s"] and not s.get("ref")),key=lambda s:s["s"]["5Y"]["avg"])
totaum=sum(f["aum"] or 0 for f in F)
answers=[
 dict(q="Highest-returning fund type",a=t5["sub"],d=f"{t5['s']['5Y']['avg']:+.1f}% a year over 5 years across {t5['s']['5Y']['n']} funds. Over 10 years: {t10['sub']} at {t10['s']['10Y']['avg']:+.1f}%.",tab="returns"),
 dict(q="Best AMC across categories",a=a5["a"],d=f"Its funds sit at the {a5['s']['5Y']['pct']:.0f}th percentile of their peer groups on 5 years ({a5['s']['5Y']['n']} funds). On 10 years: {a10['a']} ({a10['s']['10Y']['pct']:.0f}th).",tab="amc"),
 dict(q="Best single fund",a=f5["n"],d=f"{f5['r']['5Y']:+.1f}% a year over 5 years ({f5['sub']}). Over 10 years: {f10['n']} at {f10['r']['10Y']:+.1f}%.",tab="amc"),
 dict(q="Highest-fee AMC",a=terCall["hiR"]["a"],d=f"Average regular-plan TER of {terCall['hiR']['r']:.2f}% across {terCall['hiR']['n']} active equity funds. Cheapest: {terCall['lo']['a']} at {terCall['lo']['d']:.2f}% direct.",tab="costs"),
 dict(q="Best return for the cost (active equity)",a=e5["n"],d=f"{e5['r']['5Y']:+.1f}% a year over 5 years on a {e5['ter']:.2f}% TER, {e5['r']['5Y']/e5['ter']:.0f}× its cost.",tab="costs"),
 dict(q="Best-returning style",a=st5["label"],d=f"{st5['s']['5Y']['avg']:+.1f}% a year over 5 years across {st5['s']['5Y']['n']} funds.",tab="styles"),
 dict(q="Best ELSS now",a=bestE["n"],d=f"ELSS funds average {el_s['3Y']['avg']:+.1f}% over 3 years and {el_s['5Y']['avg']:+.1f}% over 5. This one returned {bestE['r']['5Y']:+.1f}% over 5.",tab="elss"),
]
kpi=[dict(l="Schemes analysed",v=f"{len(F):,}",s=f"{sum(1 for f in F if f.get('etf'))} ETFs · {sum(1 for f in F if not f.get('etf'))} funds"),dict(l="Fund houses",v=str(len(byamc)),s=f"{len(amc)} with enough history to rank"),
     dict(l="Sub-categories",v=str(len(cats)),s="across 5 asset categories"),dict(l="Assets covered",v=f"₹{totaum/100000:.1f} lakh cr",s="sum of scheme AUM"),
     dict(l="With 10-year history",v=str(sum(1 for f in F if '10Y' in f['r'])),s=f"{sum(1 for f in F if '5Y' in f['r'])} with 5 years · {sum(1 for f in F if '3Y' in f['r'])} with 3"),]
lede=f"{len(F):,} growth-option schemes from {len(byamc)} fund houses, with returns computed from month-end NAVs to 30 September 2026. Each card below answers one of the questions this section set out to cover; open it for the full ranking."
method=[
 "Source: Pulse Labs PulseDB API (screener, NAV history, metadata, analytical data, risk parameters), pulled on 3 October 2026.",
 f"Universe: every active scheme Pulse lists with a growth option. The direct plan is used where it exists ({sum(1 for f in F if not f.get('etf'))} schemes); ETFs and a few schemes with a single plan make up the rest. {sif} Specialized Investment Fund strategies are excluded because they are a separate product with no return history yet.",
 "Returns: computed from month-end NAVs, 30 September 2026 against the same month-end 1, 3, 5 and 10 years earlier. Periods over one year are compound annual growth rates. They match Pulse's own trailing-return API to within 0.02 points on 5 and 10 years.",
 "Returns are net of expenses and before tax and exit load. A fund appears in a period only if it existed for the whole period, so 10-year figures cover survivors only and flatter the average.",
 "Category averages are simple averages of funds; the median and AUM-weighted average are one click away. Sub-category names are Pulse's.",
 "AMC score: each actively managed fund is ranked against active peers in its sub-category (groups of 5 or more), giving a percentile from 0 to 100. The AMC score is the average percentile of its funds. Index funds, ETFs, funds of funds, target-maturity and commodity funds are left out because they track a benchmark.",
 f"Expense ratios are the latest TER Pulse reports, and many regular plans of small schemes show 3% or more, above SEBI's base ceiling, which suggests Pulse's figure includes statutory levies. {NBAD} schemes with implausible values (active funds above 3% direct or 4.5% regular, index funds and ETFs above 1.5%) are left out of fee rankings and remain in the explorer.",
 f"NAV series of {NSPLIT} schemes, mostly ETFs, show a unit split (NAV falling to a tenth, a fiftieth or a hundredth in one month). Earlier NAVs are rescaled so returns are not distorted.",
 "Growth, blend and value tilt: diversified active equity funds are sorted by portfolio P/E relative to their sub-category median and split into thirds. P/E is today's portfolio, so this describes how the fund is positioned now, not across the whole period.",
 "ELSS score: average of the fund's percentile within ELSS on 3, 5 and 10-year return and 3-year Sharpe ratio (Pulse risk API). Funds need at least 5 years of history to be scored.",
 "Star ratings and riskometer levels are passed through from Pulse. Past returns do not predict future returns; none of this is investment advice.",
]
for f in F:
    del f["_bad"]
    for k in [k for k,v in f.items() if v is None]: del f[k]
D=dict(asof="30 Sep 2026",H=H,catOrder=CATS,kpi=kpi,lede=lede,answers=answers,broad=broad,cats=cats,amc=amc,amcCat=amcCat,amcMin=AMIN,best=best,cons=cons,terCat=terCat,amcTer=amcTer,terCall=terCall,eff=eff,styles=styles,peStyle=peStyle,
       peNote=f"{len(rel)} diversified active equity funds split into thirds by portfolio P/E relative to their own sub-category.",capStyle=capStyle,elss=elss,sif=sif,method=method,funds=F)
html=open("template.html").read().replace("/*DATA*/",json.dumps(D,separators=(",",":"),ensure_ascii=False).replace("</","<\\/").replace("\ufffd","-"))
open("dashboard.html","w").write(html)
# standalone page for GitHub Pages (the Artifact host adds this skeleton itself)
open("index.html","w").write('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n'+html); json.dump(D,open("data.json","w"))
print("dashboard.html",len(html)//1024,"KB")
for a in answers: print("-",a["q"],"|",a["a"],"|",a["d"])
print("TOP SUBS 5Y",[(c["sub"],c["s"]["5Y"]["avg"],c["s"]["5Y"]["n"]) for c in sorted([c for c in cats if "5Y" in c["s"] and c["s"]["5Y"]["n"]>=3],key=lambda c:-c["s"]["5Y"]["avg"])[:8]])
print("AMC 5Y",[(a["a"],a["s"]["5Y"]["pct"],a["s"]["5Y"]["n"]) for a in sorted([a for a in amc if "5Y" in a["s"]],key=lambda a:-a["s"]["5Y"]["pct"])[:8]])
print("AMCs",sorted(byamc))
print("terCat",terCat); print("amcTer top",sorted(amcTer,key=lambda a:-a["r"])[:4]); print("styles",[(s["label"],s["n"],s["s"].get("5Y",{}).get("avg")) for s in styles]); print("pe",[(p["label"],p["n"],p["pe"],p["s"].get("5Y",{}).get("avg")) for p in peStyle])
print("elss",el_s, [(F[i]["n"],score[F[i]["c"]]) for i in [elss["best"]]+elss["others"]]); print("cons",len(cons)); print("broad",[(b["cat"],b["s"].get("5Y",{}).get("avg")) for b in broad])
print("cmp",elss["cmp"])
