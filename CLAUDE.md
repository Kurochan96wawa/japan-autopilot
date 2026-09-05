# japan-autopilot (littletabi.com) — operating rules for Claude Code

Public repo. Never commit API keys, emails, phone numbers, revenue figures or personal names. Commit author must be the GitHub noreply address (already configured in the account).

## What this is
Static site (docs/) for littletabi.com — "Japan with kids" family-travel guides — built by a Python pipeline (src/) and deployed by Cloudflare Pages from `docs/`. GitHub Actions run the pipeline on a schedule (daily-post: Mon/Thu 22:00 UTC; weekly-improve; weekly-review; extras on demand).

## Non-negotiable rules
1. **No fabrication.** Prices, room sizes, opening hours, policies and named places must come from an official/primary source that you actually fetched. If it is not stated, write "not stated" or leave it out. Never invent affiliate links; copy existing ones from the codebase.
2. **docs/ is generated. Do not hand-edit docs/.** User-visible changes go into src/ (fixups, templates) or assets/pages/ (hand-built pages, copied to docs/ every run by `quality_fixups._build_static_pages`).
3. **Fail-closed CI stays.** `src/ci_assert.py`, `src/link_linter.py`, `python -m src.ideas --selftest`, `python -m src.linker --selftest` must be green before any push. Do not weaken an assertion to make a build pass; fix the cause.
4. **301s have one source of truth:** `linker.REDIRECT_MAP` → generates `docs/_redirects`, canonicals, sitemap exclusions.
5. **Clusters:** `config/clusters.yaml` drives hubs, related links and ci_assert. New articles are auto-assigned by `linker.auto_assign()`; hand-edits must keep the YAML comments.
6. Hand-built pages in `assets/pages/` are skipped by site.py backfill, seo.py title rewrites and weekly Fixable regeneration — keep it that way.

## Local verification (no API keys needed)
```
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m src.main rebuild
python -m src.leadmagnet && python -m src.seo_fixups && python -m src.quality_fixups && python -m src.facts_fixups
python -m src.webstory || true
python -m src.link_linter
python -m src.ideas --selftest
python -m src.linker --selftest
python -m src.ci_assert
```
All must exit 0. `git status` after the chain should show only date/timestamp churn (page_dates.json, hubs, sitemap, PDF) — anything else is a real change to inspect. IndexNow ping fails offline; that is harmless.

## Workflow
- Branch → PR → self-merge is fine (`gh pr create`, `gh pr merge --squash`). Write what was verified in the PR body.
- Trigger runs: `gh workflow run daily.yml -f mode=rebuild` (no LLM, deploys docs) · `gh run watch` · `gh run view <id> --log-failed`.
- After merging anything that changes docs, run a `rebuild` so Cloudflare Pages deploys it.
- Save a short work report (Japanese) to the Cowork knowledge folder when a task is done, if that folder was passed with `--add-dir`.

## Money pages and affiliates
- Working programs (Travelpayouts marker 744378 / Klook aid 125283): Welcome Pickups, Radical Storage, Klook. Booking.com links are present but unmonetised (program not yet approved).
- ci_assert requires ≥3 working CTAs on `docs/best-family-hotels-tokyo-connecting-rooms.html`.
- When a hotel affiliate program (Trip.com / Agoda) is approved, replace the `See rates` link builder in `assets/pages/best-family-hotels-tokyo-connecting-rooms.html` (currently Booking search URLs) — one place.

## Content strategy (what to build next)
Prefer verified comparison pages with commercial intent over generic articles: e.g. Kyoto/Osaka family hotels with kitchens, Tokyo Disney Resort area hotels, apartments for 6+. Same method as the Tokyo hotels page: official room pages only, no prices, comparison table + FAQ JSON-LD + CTAs + Kit form. Put them in `assets/pages/` and register in `quality_fixups.STATIC_PAGES` and `config/clusters.yaml`.

## Known pitfalls
- `site.rebuild_index` backfill rewraps pages; hand-built pages must be restored after main (already handled).
- Cloudflare Pages redirects `/x.html` → `/x` (308); canonicals still use `.html` — planned cleanup: move canonical/sitemap/internal links to extensionless URLs consistently.
- The quality gate can discard a generated article and the topic is consumed; consider re-queuing on discard.
