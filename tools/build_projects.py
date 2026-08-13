#!/usr/bin/env python3
"""Generate projects.json for the portfolio section (issue 20).

Run from anywhere:

    python3 tools/build_projects.py

Writes projects.json at the repository root. Standard library only, and run by
hand like tools/optimize_images.py and tools/make_og_card.py rather than as
part of a build: this site has no build step, and the data changes about as
often as the repos do.

Why a generated file at all. The renderer used to call the GitHub API three
times per page load, once per account. The unauthenticated limit is 60 requests
per hour per IP address, which is roughly 20 page loads from a shared address
before the section shows an error instead of any work. That is fine for one
visitor and not fine for anyone behind a corporate NAT or a university network,
which describes a fair number of the nonprofits and researchers this site is
aimed at. A committed file makes the failure mode structurally impossible: a
visitor fetches one same-origin static file and never talks to GitHub.

Set GITHUB_TOKEN or GH_TOKEN to raise this script's own rate limit. It is
optional: two requests fits inside the unauthenticated limit comfortably.

Re-run this after adding the portfolio topic to a repo, after editing a
description, or after redeploying a demo that had gone dark. Nothing runs it
for you, which is the accepted cost of having no CI in this repository.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "projects.json"

# MapTheVoteSTL was removed on 2026-08-13 (issue 20, criterion 4). Its one
# repo has no description and no topic, so it could never contribute a card.
#
# Seaside-Sustainability-Web-GIS stays even though it contributes nothing
# today: both of its matching repos are archived forks and are filtered out
# below. With no visitor-side API call, an account that matches nothing costs
# nothing, and leaving it configured means a future repo there appears without
# a code change.
ACCOUNTS = [
    "GeoBradDev",
    "Seaside-Sustainability-Web-GIS",
]

# GitHub topics are the intended mechanism for this. The old filter looked for
# the word "portfolio" in the description, which put a control flag in copy a
# visitor to the repo reads, and broke silently whenever a description got
# reworded.
PORTFOLIO_TOPIC = "portfolio"

API = "https://api.github.com/users/%s/repos?per_page=100&sort=updated"
USER_AGENT = "geobrad.dev-build-projects"
FETCH_TIMEOUT = 30
PROBE_TIMEOUT = 15


def https_url(value):
    """The URL if it parses and is https, else None.

    Mirrors safeUrl() in index.html on purpose. The renderer validates again at
    render time, because a hand-edited projects.json is still untrusted input;
    this half keeps a javascript: or http: homepage from ever being written to
    the file in the first place.
    """
    if not isinstance(value, str) or value == "":
        return None
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return value


def select_repos(repos):
    """Repos carrying the portfolio topic that are not archived.

    Archived is excluded because an archived repo is frozen: its demo is
    usually gone, its description cannot be edited to fix anything, and it is
    weaker portfolio material than anything still moving. The two CleanUpCoop
    forks under Seaside-Sustainability-Web-GIS are exactly that case.
    """
    selected = []
    for repo in repos:
        topics = repo.get("topics") or []
        if PORTFOLIO_TOPIC not in topics:
            continue
        if repo.get("archived"):
            continue
        selected.append(repo)
    return selected


def collect(accounts, fetch_repos):
    """Every account's repos, tolerating a failure in any one of them.

    Returns (repos, failed_accounts). One account being rate limited, renamed,
    or 502ing used to throw and leave the whole section blank; now it costs
    only its own repos.

    Every account failing is a different situation and raises: there is no
    partial result to keep, and writing an empty projects.json would blank the
    section far more thoroughly than the bug this guards against.
    """
    repos = []
    failed = []
    for account in accounts:
        try:
            repos.extend(fetch_repos(account))
        except Exception as error:  # noqa: BLE001 - one bad account is not fatal
            failed.append(account)
            print("  WARN  %s failed: %s" % (account, error), file=sys.stderr)
    if failed and len(failed) == len(accounts):
        raise RuntimeError("every account failed; refusing to write an empty file")
    return repos, failed


def resolve_demo(homepage, probe):
    """The homepage if it is https and answers, else None.

    Six of the nine repos this section used to show pointed at Render's free
    tier, and four of those had 404'd outright by 2026-08-13. A Live Demo link
    to a dead page is worse than no link, so a URL that does not answer here
    never reaches projects.json and the card renders with a Code link alone.
    """
    url = https_url(homepage)
    if url is None:
        return None
    return url if probe(url) else None


def to_project(repo, demo):
    """One repo as the record the renderer consumes.

    description and language are "" rather than null when GitHub supplies
    nothing, so the renderer's `||` fallbacks stay simple and the schema has
    one nullable field instead of three.
    """
    return {
        "name": repo.get("name") or "",
        "description": repo.get("description") or "",
        "language": repo.get("language") or "",
        "stars": int(repo.get("stargazers_count") or 0),
        "code": https_url(repo.get("html_url")),
        "demo": demo,
        "pushed": repo.get("pushed_at") or "",
    }


def request(url):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, headers=headers)


def fetch_repos(account):
    with urllib.request.urlopen(request(API % account),
                                timeout=FETCH_TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("expected a list of repos, got %s" % type(data).__name__)
    return data


def probe(url):
    """True when the URL answers below 400.

    GET rather than HEAD: enough hosts answer HEAD with 405 that a HEAD probe
    would drop demos that are perfectly alive.
    """
    try:
        with urllib.request.urlopen(request(url), timeout=PROBE_TIMEOUT) as response:
            return response.status < 400
    except urllib.error.HTTPError as error:
        return error.code < 400
    except Exception:  # noqa: BLE001 - anything else is a link a visitor cannot use
        return False


def main():
    repos, failed = collect(ACCOUNTS, fetch_repos)

    # pushed_at, not updated_at. updated_at bumps on any repo metadata change:
    # a description edit, a topic change, someone starring it, a settings
    # toggle. Stripping the #portfolio flag from seven descriptions on
    # 2026-08-13 reset all seven to the same minute and flattened the order
    # into whichever sequence the PATCH calls happened to run in. pushed_at
    # moves only on a real push, which is what "most recently worked on"
    # was always trying to mean.
    selected = sorted(select_repos(repos),
                      key=lambda r: r.get("pushed_at") or "", reverse=True)

    for account in ACCOUNTS:
        if account in failed:
            continue
        count = sum(1 for r in selected
                    if (r.get("owner") or {}).get("login") == account)
        print("  %-32s %d project(s)" % (account, count))

    if not selected:
        print("No repo carries the %r topic. Refusing to write an empty file."
              % PORTFOLIO_TOPIC, file=sys.stderr)
        return 1

    projects = []
    for repo in selected:
        demo = resolve_demo(repo.get("homepage"), probe)
        if repo.get("homepage") and demo is None:
            print("  WARN  %s homepage %s did not answer; shipping without a demo link"
                  % (repo.get("name"), repo.get("homepage")), file=sys.stderr)
        if "#portfolio" in (repo.get("description") or "").lower():
            print("  WARN  %s description still carries the #portfolio flag"
                  % repo.get("name"), file=sys.stderr)
        projects.append(to_project(repo, demo))

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "projects": projects,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print("Wrote %s with %d project(s)." % (OUTPUT.relative_to(ROOT), len(projects)))
    if failed:
        print("  %d account(s) failed and contributed nothing: %s"
              % (len(failed), ", ".join(failed)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
