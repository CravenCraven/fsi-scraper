"""fsi-scraper command line interface.

`discover` walks a course and reports every downloadable asset. It writes
nothing and downloads no course material -- that is `fetch`.

Some courses are one page; others are an index plus a page per unit. The
crawl handles both: it follows whatever `parser.follow()` yields, visits each
page once, and sleeps between requests.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import requests

from .models import Resource
from .sources import base, fsi_fast, fsi_programmatic  # noqa: F401

USER_AGENT = (
    "fsi-scraper/0.1 (+https://github.com/CravenCraven/fsi-scraper) "
    "personal study corpus"
)
DEFAULT_DELAY = 1.0


class Fetcher:
    """HTTP with a shared session, a delay between requests, and a page cache."""

    def __init__(self, delay: float = DEFAULT_DELAY, cache: Path | None = None):
        self.delay = delay
        self.cache = cache
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last = 0.0
        self.requests_made = 0

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache:
            return None
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in url)[-150:]
        return self.cache / f"{safe}.html"

    def get(self, url: str) -> str:
        cached = self._cache_path(url)
        if cached and cached.exists():
            return cached.read_text(encoding="utf-8")

        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)

        response = self.session.get(url, timeout=30)
        self._last = time.monotonic()
        self.requests_made += 1
        response.raise_for_status()

        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(response.text, encoding="utf-8")
        return response.text


def crawl(
    parser: base.CourseParser,
    fetcher: Fetcher,
    start: str,
    max_pages: int = 200,
    progress: bool = True,
) -> list[Resource]:
    queue = [start]
    visited: set[str] = set()
    by_url: dict[str, Resource] = {}

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            html = fetcher.get(url)
        except requests.RequestException as exc:
            print(f"  ! {url}: {exc}", file=sys.stderr)
            continue

        for resource in parser.parse(html, url):
            by_url.setdefault(resource.url, resource)

        for follow_url in parser.follow(html, url):
            if follow_url not in visited:
                queue.append(follow_url)

        if progress:
            print(f"  [{len(visited)}] {len(by_url)} assets  {url}", file=sys.stderr)

    if len(visited) >= max_pages and queue:
        print(
            f"  ! stopped at --max-pages {max_pages}, {len(queue)} still queued",
            file=sys.stderr,
        )

    return sorted(
        by_url.values(),
        key=lambda r: (r.section or "", r.ordinal or 0, r.kind, r.filename),
    )


def print_table(resources: list[Resource]) -> None:
    width = max((len(r.title) for r in resources), default=10)
    for r in resources:
        print(f"{r.kind:<5}  {r.section or '-':<9}  {r.title:<{width}}  {r.filename}")


def summarise(resources: list[Resource]) -> str:
    counts: dict[str, int] = {}
    for r in resources:
        counts[r.kind] = counts.get(r.kind, 0) + 1
    parts = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    ordinals = {r.ordinal for r in resources if r.ordinal}
    span = f"; units {min(ordinals)}-{max(ordinals)}" if ordinals else ""
    return f"{len(resources)} assets: {parts}{span}"


def cmd_discover(args: argparse.Namespace) -> int:
    parser = base.get(args.course)

    if args.page and not args.page.startswith(("http://", "https://")):
        resources = sorted(
            {r.url: r for r in parser.parse(
                Path(args.page).read_text(encoding="utf-8"), parser.page_url
            )}.values(),
            key=lambda r: (r.section or "", r.ordinal or 0, r.kind),
        )
    else:
        fetcher = Fetcher(delay=args.delay,
                          cache=Path(args.cache) if args.cache else None)
        resources = crawl(
            parser, fetcher, args.page or parser.page_url,
            max_pages=args.max_pages,
        )
        print(f"  {fetcher.requests_made} requests made", file=sys.stderr)

    if not resources:
        print("no resources found -- page markup may have changed", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(
            [dataclasses.asdict(r) for r in resources], indent=2, default=str
        ))
    else:
        print_table(resources)

    print(f"\n{summarise(resources)}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fsi-scraper")
    sub = ap.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="list downloadable assets for a course")
    d.add_argument("--course", default="brazilian-portuguese-fast",
                   choices=base.registered())
    d.add_argument("--page", help="override the start URL, or a path to saved HTML")
    d.add_argument("--format", choices=("table", "json"), default="table")
    d.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                   help="seconds between HTTP requests (default 1.0)")
    d.add_argument("--cache", help="directory to cache fetched pages in")
    d.add_argument("--max-pages", type=int, default=200)
    d.set_defaults(func=cmd_discover)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
