# Internship alert bot

Checks published postings for Summer 2027 internships and records the health of **every company** in `companies.csv`. GitHub Actions runs every six hours, emails newly detected matches, and sends a Monday coverage report. See [source_health.md](source_health.md) for the current company-by-company status.

## How the two adapters work

1. **Structured job feeds**: official public Ashby, Greenhouse, and Lever posting endpoints. Configure `source_type` and `source_key` for a known board. The feed's stable posting ID is used for deduplication.
2. **Public HTML job listings**: opt-in only. Configure `source_type=html`, an exact `job_selector` for detail links, and a `job_url_pattern`. The adapter checks robots.txt before requesting the page. Do not add a site if its access terms forbid automation; use an authorized feed, employer alerts, or manual review instead.

The existing company list is retained, but companies without a configured and checked source are marked **unconfigured**. They do **not** produce alerts. This prevents the old broad career-page link scan from reporting navigation, category links, and stale listings as jobs. The initial successful check of a newly configured source establishes its baseline, so already published jobs are not re-sent as new releases.

As of this update, 37 of 188 companies have individually tested live public feeds; 151 are unconfigured and clearly reported. A live feed returning no jobs is `empty`; a failed request is `error`; robots denial is `blocked`. No source is claimed as verified simply because the workflow succeeded.

## Verification and notification

- `source_health.json` and `source_health.md` show status, posting count, matching count, and error for each company at the last check. The same table appears in the GitHub Actions run summary.
- `verify.py` checks that every configured source returned a current verification result. The workflow fails if a configured source errors or is blocked. It reports the count of unconfigured sources separately.
- If a previously working source errors or becomes blocked, an email is sent on the transition. A weekly email gives the full coverage report, including unconfigured companies.
- Only a new stable posting ID from a previously baselined source triggers an internship email. Saved legacy URLs suppress duplicates during migration. The matching rule uses the **job title** for internship and seniority, not the surrounding careers-page text. It uses the title and department for the role category.
- Job listings without a year in the title may be included; review the linked posting for eligibility and Summer 2027 dates. Zero matches can mean no relevant openings, so the verifier cannot promise a job will be posted.

## Adding a company source

Find the actual employer job board and its published posting feed. Test that it returns a `jobs` array with current job IDs, titles, and direct URLs; set `source_type=ashby` or `greenhouse` and its board key. For Lever, set `source_type=lever` and its site key. If only an HTML page exists, confirm automation is permitted, define a selector matching only job detail links, set the URL pattern, and test the resulting report. Never bypass a 403, CAPTCHA, robots restriction, or authentication.

Run locally:

```bash
pip install -r requirements.txt
python -m unittest -q test_monitor
python monitor.py
python verify.py
```

The workflow needs `EMAIL_USERNAME` and `EMAIL_APP_PASSWORD` repository secrets for email. Source coverage is a gradual, explicit process: `companies.csv` alone is a watchlist, not proof of active monitoring.
