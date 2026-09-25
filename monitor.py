"""Explicit job-feed and public-page adapters with per-company verification."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
AGENT = "InternshipAlertBot/2.0 (+https://github.com/aliciamiacheng/internship-alert-bot)"
session = requests.Session()
session.headers.update({"User-Agent": AGENT, "Accept": "application/json"})


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def fetch_json(url, timeout):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def api_jobs(row, timeout):
    kind, board = row["source_type"], row["source_key"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", board):
        raise ValueError("Invalid board key")
    if kind == "ashby":
        data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}", timeout)
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ValueError("Ashby feed shape changed")
        return [{"id": j.get("id") or j.get("jobUrl"), "title": j.get("title"),
                 "url": j.get("jobUrl"), "location": j.get("location"),
                 "department": j.get("department"), "employment": j.get("employmentType")}
                for j in data["jobs"] if j.get("isListed", True)]
    if kind == "greenhouse":
        data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", timeout)
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ValueError("Greenhouse feed shape changed")
        return [{"id": j.get("id"), "title": j.get("title"), "url": j.get("absolute_url"),
                 "location": (j.get("location") or {}).get("name"),
                 "department": " ".join(d.get("name", "") for d in j.get("departments", []))}
                for j in data["jobs"]]
    if kind == "lever":
        jobs = []
        for skip in range(0, 10000, 100):
            page = fetch_json(f"https://api.lever.co/v0/postings/{board}?mode=json&skip={skip}&limit=100", timeout)
            if not isinstance(page, list):
                raise ValueError("Lever feed shape changed")
            jobs.extend({"id": j.get("id"), "title": j.get("text"), "url": j.get("hostedUrl"),
                         "location": (j.get("categories") or {}).get("location"),
                         "department": (j.get("categories") or {}).get("team"),
                         "employment": (j.get("categories") or {}).get("commitment")}
                        for j in page)
            if len(page) < 100:
                return jobs
        raise ValueError("Lever pagination limit reached")
    raise ValueError(f"Unsupported source: {kind}")


def html_jobs(row, timeout):
    """Opt-in adapter: strict selector and job URL pattern; obey robots.txt."""
    url, selector = row["careers_url"], row["job_selector"]
    if not selector or not row["job_url_pattern"]:
        raise ValueError("HTML source needs job_selector and job_url_pattern")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("HTML source needs HTTPS")
    robots_response = session.get(f"https://{parsed.netloc}/robots.txt", timeout=timeout)
    robots_response.raise_for_status()
    robots = RobotFileParser()
    robots.parse(robots_response.text.splitlines())
    if not robots.can_fetch(AGENT, url):
        raise PermissionError("robots.txt disallows the listing page")
    response = session.get(url, timeout=timeout, headers={"Accept": "text/html"})
    response.raise_for_status()
    pattern = re.compile(row["job_url_pattern"])
    result = []
    for link in BeautifulSoup(response.text, "html.parser").select(selector):
        if link.name != "a" or not link.get("href"):
            continue
        href = urljoin(url, link["href"])
        if urlparse(href).scheme == "https" and pattern.search(href):
            result.append({"id": href, "title": clean(link.get_text(" ", strip=True)),
                           "url": href, "location": "", "department": ""})
    return result


def matches(job, cfg):
    title = clean(job.get("title"))
    role = f"{title} {clean(job.get('department'))}".lower()
    details = f"{title} {clean(job.get('employment'))}".lower()
    if not re.search(r"\b(intern|internship|summer analyst|summer associate)\b", details):
        return []
    if re.search(r"\b(senior|staff|director|principal|lead|graduate programme)\b", title.lower()):
        return []
    years = re.findall(r"\b20\d{2}\b", title)
    if years and not set(years).intersection(map(str, cfg["target"]["internship_years"])):
        return []
    if cfg["target"].get("exclude_remote") and re.search(r"\bremote\b", clean(job.get("location")).lower()):
        return []
    return [category for category, terms in cfg["categories"].items()
            if any(re.search(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", role) for term in terms)]


def report_md(state):
    counts = {}
    for item in state["companies"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    lines = ["# Internship source verification", "", f"Checked: {state['checked_at_utc']}", "",
             " | ".join(f"{k}: {v}" for k, v in sorted(counts.items())), "",
             "A successful run does not mean every company is monitored. Unconfigured and error sources need attention.",
             "", "| Company | Source | Status | Listings | Matches | Detail |",
             "|---|---|---|---:|---:|---|"]
    for item in state["companies"]:
        fields = [item["company"], item["source"], item["status"], str(item["listings"]),
                  str(item["matches"]), item["detail"].replace("|", "/")]
        lines.append("| " + " | ".join(fields) + " |")
    return "\n".join(lines) + "\n"


def run():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    previous_health_path = ROOT / "source_health.json"
    previous_health = json.loads(previous_health_path.read_text()) if previous_health_path.exists() else {}
    previous_status = {item["company"]: item["status"] for item in previous_health.get("companies", [])}
    with (ROOT / "companies.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    seen_path = ROOT / "seen_jobs.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    sources = seen.pop("_sources", {})
    previous_sources = set(sources)
    health, fresh = [], []
    (ROOT / "new_matches_found.txt").write_text("false\n")
    for row in rows:
        name, kind = row["company"], row["source_type"]
        entry = {"company": name, "source": kind or "none", "status": "unconfigured",
                 "listings": 0, "matches": 0, "detail": "No approved listing source configured"}
        if kind:
            try:
                raw = html_jobs(row, cfg["settings"]["request_timeout_seconds"]) if kind == "html" else api_jobs(row, cfg["settings"]["request_timeout_seconds"])
                entry.update(status="ok" if raw else "empty", listings=len(raw), detail="")
                old_urls = {v.get("url") for v in seen.values() if isinstance(v, dict) and v.get("company") == name}
                for job in raw:
                    url, title = clean(job.get("url")), clean(job.get("title"))
                    if not job.get("id") or not title or not url.startswith("https://"):
                        continue
                    categories = matches(job, cfg)
                    if not categories:
                        continue
                    entry["matches"] += 1
                    stable_id = hashlib.sha256(f"v2|{name}|{job['id']}".encode()).hexdigest()[:32]
                    result = {"company": name, "title": title, "url": url, "id": stable_id,
                              "categories": categories, "location": clean(job.get("location"))}
                    if stable_id not in seen and name in previous_sources and url not in old_urls:
                        fresh.append(result)
                    seen[stable_id] = result
                sources[name] = {"last_success_utc": datetime.now(timezone.utc).isoformat(),
                                 "last_count": len(raw)}
            except (requests.RequestException, ValueError, PermissionError, re.error) as exc:
                entry.update(status="blocked" if isinstance(exc, PermissionError) else "error",
                             detail=f"{type(exc).__name__}: {str(exc)[:180]}")
        health.append(entry)
        print(f"{name}: {entry['status']} ({entry['listings']} listings, {entry['matches']} matches) {entry['detail']}")
    seen["_sources"] = sources
    seen_path.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n")
    state = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "companies": health}
    (ROOT / "source_health.json").write_text(json.dumps(state, indent=2) + "\n")
    (ROOT / "source_health.md").write_text(report_md(state))
    regressions = [x for x in health if previous_status.get(x["company"]) == "ok"
                   and x["status"] in ("error", "blocked", "empty")]
    (ROOT / "health_errors_found.txt").write_text("true\n" if regressions else "false\n")
    (ROOT / "health_alert.md").write_text(
        "# Internship sources need attention\n\n" +
        "\n".join(f"- {x['company']}: {x['status']} — {x['detail']}" for x in regressions) + "\n"
        if regressions else "# No newly broken sources\n")
    lines = ["# New Summer 2027 internship matches", ""]
    for job in fresh:
        lines.extend([f"## {job['company']} — {job['title']}",
                      f"Categories: {', '.join(job['categories'])}",
                      f"Location: {job['location'] or 'Not specified'}",
                      f"Apply: {job['url']}", ""])
    (ROOT / "latest_alert.md").write_text("\n".join(lines) + "\n" if fresh else "# No new matching internships\n")
    (ROOT / "new_matches_found.txt").write_text("true\n" if fresh else "false\n")
    print(f"New matches: {len(fresh)}. Active sources: {sum(x['status'] == 'ok' for x in health)}/{len(health)}.")


if __name__ == "__main__":
    run()
