"""robots.txt tests. No network: rules are written into the notebook by hand."""

from urllib import robotparser

import pytest
import requests

from fsi_scraper.cli import Fetcher


def fetcher_with_rules(site: str, lines: list[str]) -> Fetcher:
    fetcher = Fetcher(delay=0)
    rules = robotparser.RobotFileParser()
    rules.parse(lines)
    fetcher._robots[site] = rules
    return fetcher


def test_disallowed_path_is_blocked():
    fetcher = fetcher_with_rules("https://example.com",
                                 ["User-agent: *", "Disallow: /private/"])

    assert fetcher.allowed("https://example.com/private/file.pdf") is False
    assert fetcher.allowed("https://example.com/public/file.pdf") is True


def test_second_request_to_same_site_still_answers():
    fetcher = fetcher_with_rules("https://example.com",
                                 ["User-agent: *", "Disallow: /private/"])

    assert fetcher.allowed("https://example.com/public/a.pdf") is True
    assert fetcher.allowed("https://example.com/public/b.pdf") is True


def test_stream_refuses_blocked_url():
    fetcher = fetcher_with_rules("https://example.com",
                                 ["User-agent: *", "Disallow: /private/"])

    with pytest.raises(requests.RequestException, match="blocked by robots.txt"):
        fetcher.stream("https://example.com/private/file.pdf")
