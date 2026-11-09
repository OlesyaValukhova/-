"""Collect the verified public program API, or parse saved pages/browser bundle.

Python 3.10+, standard library only. Never infers ages or program venues.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from collect_navigator import PublicRedirect, page_payload, public_url

URL = ("https://dopobr.petersburgedu.ru/api/program/list_odo/"
       "?district=2&limit=10&offset=0&ordering=rating_avg_desc&page=1")


def validate_url(url):
    public_url(url)
    if urlsplit(url).path.rstrip("/") != "/api/program/list_odo":
        raise ValueError("Not the verified program-list API")
    return url


def aggregate(pages):
    records = {}
    warnings = []
    totals = set()
    terminal = False
    starts_at_zero = False
    filters = None
    expected_next = None
    for index, page in enumerate(pages):
        data = page_payload(json.dumps(page["response"], ensure_ascii=False))
        url = page.get("url")
        if url:
            validate_url(url)
            params = dict(parse_qsl(urlsplit(url).query))
            current_filters = {k: v for k, v in params.items()
                               if k not in {"offset", "page", "limit"}}
            if filters is None:
                filters = current_filters
                starts_at_zero = params.get("offset", "0") == "0" and not data.get("previous")
            elif current_filters != filters:
                raise ValueError("Cannot combine pages with different filters/sort order")
        else:
            warnings.append("Source request URL missing; coverage cannot be certified")
        if index and expected_next != url:
            warnings.append("Pages are not a verified consecutive chain")
        totals.add(data["count"])
        if data.get("next"):
            validate_url(data["next"])
        expected_next = data.get("next")
        terminal = "next" in data and data["next"] is None
        for row in data["results"]:
            item_id = row.get("id")
            if not isinstance(item_id, int) or isinstance(item_id, bool):
                raise ValueError("Program missing integer ID")
            if item_id in records:
                warnings.append(f"Duplicate program ID {item_id}")
                if records[item_id] != row:
                    warnings.append(f"Conflicting versions of program {item_id}; first retained")
            else:
                records[item_id] = row
    if len(totals) > 1:
        warnings.append("API count changed during collection")
    count = next(iter(totals)) if len(totals) == 1 else None
    complete = bool(pages) and starts_at_zero and terminal and count == len(records) and not warnings
    return list(records.values()), {"declared_count": count, "unique_programs": len(records),
                                   "page_count": len(pages), "complete_filtered_catalogue": complete,
                                   "complete_unfiltered_api_catalogue": complete and filters is not None
                                   and not (set(filters) - {"ordering"}),
                                   "complete_city_export": False, "filters": filters,
                                   "warnings": sorted(set(warnings)), "next": expected_next}



def checkpoint(output, pages):
    target = output / "pages.json"
    temporary = output / "pages.json.tmp"
    temporary.write_text(json.dumps({"format": "navigator-public-pages-v1", "pages": pages},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def fetch_page(opener, url, timeout, retries, attempts, sleep=time.sleep):
    for retry in range(retries + 1):
        attempt = {"url": url, "requested_utc": datetime.now(timezone.utc).isoformat(), "retry": retry}
        attempts.append(attempt)
        try:
            with opener.open(Request(url, headers={"User-Agent": "NIR-public-catalogue/1.0",
                                                   "Accept": "application/json"}), timeout=timeout) as response:
                raw = response.read(10_000_001)
                if len(raw) > 10_000_000:
                    raise ValueError("Response too large")
                attempt.update(status=response.status, final_url=response.url,
                               sha256=hashlib.sha256(raw).hexdigest())
                return raw
        except (OSError, URLError) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, HTTPError) and exc.code not in {408, 429, 500, 502, 503, 504}:
                raise
            if retry == retries:
                raise
            delay = min(60, 5 * 2 ** retry)
            if isinstance(exc, HTTPError):
                value = exc.headers.get("Retry-After", "") if exc.headers else ""
                if value.isdigit():
                    if int(value) > 60:
                        raise  # Leave longer server cooldowns for a later resumed run.
                    delay = max(delay, int(value))
            print(f"Temporary connection error; retry {retry + 1}/{retries} in {delay}s", flush=True)
            sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="*", help="Saved API pages or browser bundle; no network")
    parser.add_argument("--url", default=URL)
    parser.add_argument("--direct-http", action="store_true", help="Disable environment HTTP proxies; OS routing still applies")
    parser.add_argument("--resume", type=Path, help="Continue a saved pages.json into a new output directory")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--delay", type=float, default=1)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    if args.input is not None and args.resume:
        parser.error("--input and --resume are mutually exclusive")
    if not 0 <= args.retries <= 5:
        parser.error("retries=0..5")
    if not 1 <= args.max_pages <= 1000 or args.delay < 1 or not 0 < args.timeout <= 60:
        parser.error("max-pages=1..1000, delay>=1, timeout=0..60")
    validate_url(args.url)
    args.output.mkdir(parents=True, exist_ok=False)
    pages, attempts = [], []
    error = None
    try:
        if args.input is not None:
            for index, source in enumerate(args.input):
                raw = source.read_bytes()
                (args.output / f"input-{index:03d}.json").write_bytes(raw)
                payload = json.loads(raw.decode("utf-8-sig"))
                if isinstance(payload, dict) and payload.get("format") == "navigator-public-pages-v1":
                    pages.extend(payload["pages"])
                else:
                    # A standalone pasted response does not prove the original request URL.
                    pages.append({"url": None, "response": payload})
        else:
            opener = build_opener(PublicRedirect(), *([ProxyHandler({})] if args.direct_http else []))
            if args.resume:
                bundle = json.loads(args.resume.read_text(encoding="utf-8-sig"))
                if bundle.get("format") != "navigator-public-pages-v1":
                    raise ValueError("Resume requires a saved page bundle")
                pages = bundle["pages"]
                _, coverage = aggregate(pages)
                if coverage["warnings"] or not pages:
                    raise ValueError("Cannot resume an empty or inconsistent page chain")
                url = coverage["next"]
                checkpoint(args.output, pages)
            else:
                url = args.url
            seen = {p["url"] for p in pages}
            for index in range(args.max_pages):
                if url is None:
                    break
                validate_url(url)
                if url in seen:
                    raise ValueError("Pagination cycle")
                seen.add(url)
                if index:
                    time.sleep(args.delay)
                print(f"Page {len(pages) + 1}: requesting...", flush=True)
                raw = fetch_page(opener, url, args.timeout, args.retries, attempts)
                (args.output / f"page-{index:04d}.json").write_bytes(raw)
                data = page_payload(raw)
                pages.append({"url": url, "response": data})
                checkpoint(args.output, pages)
                print(f"Saved {len(data['results'])} records; API total={data['count']}", flush=True)
                if "next" not in data:
                    raise ValueError("Missing next field; cannot certify pagination")
                if not data["next"]:
                    break
                if not data["results"]:
                    raise ValueError("Empty page with next link")
                url = data["next"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    (args.output / "pages.json").write_text(json.dumps(
        {"format": "navigator-public-pages-v1", "pages": pages}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        rows, summary = aggregate(pages)
    except (ValueError, KeyError, TypeError) as exc:
        rows, summary = [], {"complete_filtered_catalogue": False}
        error = error or str(exc)
    fields = sorted({key for row in rows for key in row}) or ["id", "name"]
    with (args.output / "programs.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})
    summary.update(error=error, attempts=attempts, finished_utc=datetime.now(timezone.utc).isoformat(),
                   status="error" if error else "complete" if summary["complete_filtered_catalogue"] else "partial",
                   age_group_venue_link_verified=False)
    (args.output / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "attempts"}, ensure_ascii=False, indent=2))
    return 2 if error else 0 if summary["complete_filtered_catalogue"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
