# Product Portfolio Returns

Dashboard comparing returns across asset classes. The mutual funds section is complete; other asset classes are planned.

Live page: https://adityasingh42069.github.io/mf-portfolio-dashboard/

## Rebuild

1. Put the Pulse Labs auth key in `pulse_auth.txt` (not committed).
2. `python3 fetch.py && python3 fetch_nav.py` pulls the fund universe, metadata, risk and monthly NAVs into `raw/` (cached, not committed).
3. `python3 build.py` runs the analysis and writes `dashboard.html` and `index.html` from `template.html`.
