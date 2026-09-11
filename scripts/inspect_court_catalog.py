"""Inspect available search controls with one paced request, without exporting cases."""
from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.court_judgments import BASE_URL, REFERER_PATH, CourtJudgmentClient


class SearchControls(HTMLParser):
    """Extract public filters only; never serialize hidden authentication fields."""
    FIELDS = {"Court", "TypeProc", "CategoryDisput", "TypeDispute"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.selects = {}
        self.dates = []
        self.current = None
        self.option = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        name = attrs.get("name") or attrs.get("id")
        if tag == "select":
            self.current = name if name in self.FIELDS else None
            if self.current:
                self.selects[self.current] = []
        elif tag == "option" and self.current:
            self._finish_option()
            self.option = {"value": attrs.get("value", ""), "label": ""}
        elif tag == "input" and name in {"DateFrom", "DateTo"}:
            self.dates.append({key: val for key, val in attrs.items() if key in {
                "name", "id", "value", "type", "min", "max", "placeholder",
                "data-val-range-min", "data-val-range-max",
            }})

    def handle_data(self, data):
        if self.option is not None:
            self.option["label"] += data

    def _finish_option(self):
        if self.option is not None:
            self.option["label"] = " ".join(self.option["label"].split())
            self.selects[self.current].append(self.option)
            self.option = None

    def handle_endtag(self, tag):
        if tag in {"option", "select"}:
            self._finish_option()
        if tag == "select":
            self.current = None


class DiagnosticClient(CourtJudgmentClient):
    def _checked_response(self, response):
        info = {
            "http_status": response.status_code,
            "requires_auth": response.headers.get("REQUIRES_AUTH") == "1",
        }
        location = response.headers.get("Location")
        if location:
            target = urlsplit(urljoin(response.url, location))
            # Query values, fragments, userinfo and raw headers are not printed.
            info["redirect_host"] = target.hostname
            info["redirect_path"] = target.path
        print(json.dumps(info, ensure_ascii=False), flush=True)
        return super()._checked_response(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cookie-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        with DiagnosticClient(
            args.cookie_file.read_text(encoding="utf-8-sig"),
            cookie_file=args.cookie_file,
            rate_limit_state_file=args.cookie_file.parent / ".court-request-rate.txt",
            min_interval_seconds=300,
            delay_jitter_seconds=0,
        ) as client:
            print("One request after the 300-second interval; no redirects or retries.", flush=True)
            response = client._request("GET", BASE_URL + REFERER_PATH, timeout=client.timeout)
            controls = SearchControls()
            controls.feed(response.text)
            controls.close()
            print(json.dumps({"selects": controls.selects, "date_inputs": controls.dates}, ensure_ascii=False, indent=2))
            if not controls.selects:
                print("No recognized search filters; the available scope is not confirmed.")
                return 2
        return 0
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
