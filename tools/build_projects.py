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
import re
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

API = "https://api.github.com/users/%s/repos?per_page=%d&sort=updated&page=%d"
PAGE_SIZE = 100
# A backstop, not a limit anyone is near: the largest account here has 25
# repos. It exists so a paging bug loops a bounded number of times instead of
# forever.
MAX_PAGES = 10
USER_AGENT = "geobrad.dev-build-projects"
FETCH_TIMEOUT = 30
PROBE_TIMEOUT = 15

# Codepoint ranges that carry pictographs. Repo descriptions are free text
# typed into a box on github.com, and they land on the page verbatim, so an
# emoji in one would ship. verify_portfolio.py fails the gate on it; main()
# warns here, where whoever runs the script can still go fix the description.
EMOJI_RANGES = re.compile(
    "[\u2600-\u27bf\u2b00-\u2bff\ufe0f\U0001f000-\U0001faff]"
)


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


def github_request(url):
    """A request to api.github.com, carrying the token when one is set.

    Never use this for anything but api.github.com. urllib's redirect handler
    copies every header except content-length and content-type onto the
    redirect target, so a request built here that follows a redirect to
    another host hands that host the Authorization header.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, headers=headers)


def fetch_repos(account):
    """Every public repo on the account, following pagination to the end.

    Reading only the first page would drop a portfolio repo silently once an
    account passes PAGE_SIZE repos, and sort=updated means the first to fall
    off is the least recently touched, which is exactly the long-lived project
    least likely to be noticed missing.
    """
    repos = []
    for page in range(1, MAX_PAGES + 1):
        url = API % (account, PAGE_SIZE, page)
        with urllib.request.urlopen(github_request(url),
                                    timeout=FETCH_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, list):
            raise RuntimeError("expected a list of repos, got %s" % type(data).__name__)
        repos.extend(data)
        if len(data) < PAGE_SIZE:
            return repos
    raise RuntimeError(
        "%s has more than %d repos; raise MAX_PAGES rather than shipping a "
        "silently truncated list" % (account, PAGE_SIZE * MAX_PAGES)
    )


def probe(url):
    """True when the URL answers below 400.

    Deliberately not built with github_request. This URL is whatever a repo
    owner typed into the homepage box, it can redirect anywhere, and urllib
    copies headers across a redirect, so a token attached here would be handed
    to a third-party host in plaintext. Nothing but a User-Agent goes out.

    Not the Accept header either: a host doing strict content negotiation
    answers application/vnd.github+json with a 406, which would read as dead
    and silently drop a Live Demo link from a site that is perfectly up.

    GET rather than HEAD, because enough hosts answer HEAD with 405 that a
    HEAD probe would drop demos that are alive for the same reason.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT) as response:
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
        # Warned here rather than only failed in verify_portfolio.py, because
        # the fix is on github.com and this is the moment someone is looking.
        # A pictograph found only at gate time leaves the maintainer with a
        # red check and no idea which description to go edit.
        pictographs = sorted(set(EMOJI_RANGES.findall(repo.get("description") or "")))
        if pictographs:
            print("  WARN  %s description contains %s, which will fail the gate; "
                  "edit it on github.com and re-run"
                  % (repo.get("name"),
                     ", ".join("U+%04X" % ord(c) for c in pictographs)),
                  file=sys.stderr)
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
