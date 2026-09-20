# Alicia's Internship Alert Bot

A personalized internship monitor for **Summer 2027** opportunities across consulting, product management, finance/markets, strategy, AI, startups, venture capital, and hedge funds.

## What it does
The bot checks a curated list of career pages, extracts job-like links, scores them against the role families in `config.yaml`, removes obvious senior roles, remembers listings it has already seen, and writes new matches to `latest_alert.md`.

GitHub Actions runs the monitor automatically every six hours. You can also run it manually from the Actions tab.

## Personalized role families
- Consulting: business analyst, associate consultant, management/strategy consulting
- Product: product management, product strategy, product operations
- Finance/markets: global markets, sales & trading, asset/investment management, research, credit
- Strategy: corporate/business strategy, strategic finance, BizOps and growth strategy
- AI: applied AI, AI product/strategy, machine learning and generative AI
- Startups: founder's associate, generalist, growth and business operations
- Venture capital: investment, venture and platform roles
- Hedge funds: investment research, fundamental equities, macro and selected quantitative roles

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python monitor.py
```

## Customize
Edit `config.yaml` to change target years, locations, keywords, or exclusions. Edit `companies.csv` to add/remove companies and career pages.

## Important limitation
Many modern career sites render openings with JavaScript or use ATS APIs. The first version intentionally uses a safe generic HTML monitor, so some companies may return no listings even when roles exist. Those companies should be upgraded to dedicated Greenhouse, Lever, Workday, or company-specific adapters over time.

## Next upgrades
1. Dedicated ATS adapters (Greenhouse/Lever/Workday).
2. Location-aware scoring and ranking.
3. Email/Slack/Discord notifications.
4. Daily digest with direct application links.
5. Health checks so broken career-page parsers are flagged.
