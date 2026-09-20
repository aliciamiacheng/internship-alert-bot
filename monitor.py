from __future__ import annotations
import csv, hashlib, json, re
from pathlib import Path
from urllib.parse import urljoin
import requests, yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
SEEN_FILE = ROOT / "seen_jobs.json"
ALERT_FILE = ROOT / "latest_alert.md"
FLAG_FILE = ROOT / "new_matches_found.txt"

def load_config():
    return yaml.safe_load((ROOT / "config.yaml").read_text())

def load_companies():
    with (ROOT / "companies.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_seen():
    if not SEEN_FILE.exists(): return {}
    try: return json.loads(SEEN_FILE.read_text())
    except Exception: return {}

def save_seen(seen, max_items):
    items = list(seen.items())[-max_items:]
    SEEN_FILE.write_text(json.dumps(dict(items), indent=2, sort_keys=True))

def clean(s): return re.sub(r"\s+", " ", s or "").strip()

def fingerprint(company, title, url):
    return hashlib.sha256(f"{company}|{title}|{url}".encode()).hexdigest()[:24]

def classify(text, cfg):
    t=text.lower(); hits=[]
    for category, terms in cfg["categories"].items():
        if any(term.lower() in t for term in terms): hits.append(category)
    return hits

def relevant(title, context, cfg):
    text=f"{title} {context}".lower()
    if any(x.lower() in text for x in cfg["exclude_terms"]): return False, []
    internship=any(x.lower() in text for x in cfg["internship_terms"])
    year=any(y.lower() in text for y in cfg["target"]["internship_years"])
    categories=classify(text,cfg)
    return bool(categories) and (internship or year), categories

def scrape_company(company,cfg):
    headers={"User-Agent":"Mozilla/5.0 InternshipAlertBot/1.0"}
    try:
        r=requests.get(company["careers_url"],headers=headers,timeout=cfg["settings"]["request_timeout_seconds"])
        r.raise_for_status()
    except Exception as e:
        print(f"[WARN] {company['company']}: {e}"); return []
    soup=BeautifulSoup(r.text,"html.parser"); jobs=[]; dedupe=set()
    for a in soup.find_all("a",href=True):
        title=clean(a.get_text(" ",strip=True))
        if len(title)<4: continue
        url=urljoin(company["careers_url"],a["href"])
        parent=clean(a.parent.get_text(" ",strip=True)) if a.parent else title
        ok,categories=relevant(title,parent,cfg)
        if not ok: continue
        key=(title.lower(),url)
        if key in dedupe: continue
        dedupe.add(key)
        jobs.append({"company":company["company"],"title":title,"url":url,"categories":categories})
    return jobs

def format_alert(jobs):
    lines=["# New Summer 2027 internship matches",""]
    for j in jobs:
        cats=", ".join(x.replace("_"," ").title() for x in j["categories"])
        lines += [f"## {j['company']} — {j['title']}",f"Categories: {cats}",f"Apply: {j['url']}",""]
    return "\n".join(lines)

def main():
    cfg=load_config(); seen=load_seen(); new=[]
    FLAG_FILE.write_text("false\n")
    for company in load_companies():
        print(f"Checking {company['company']}...")
        for job in scrape_company(company,cfg):
            fid=fingerprint(job["company"],job["title"],job["url"])
            if fid not in seen:
                seen[fid]=job; new.append(job)
    save_seen(seen,cfg["settings"]["max_seen_jobs"])
    if new:
        ALERT_FILE.write_text(format_alert(new))
        FLAG_FILE.write_text("true\n")
        print(format_alert(new))
    else:
        ALERT_FILE.write_text("# No new matching internships\n")
        print("No new matching internships.")

if __name__=="__main__":
    main()
