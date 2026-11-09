"""Bounded public Navigator probe. No authentication, guessed API routes or proxies.

Requires Python 3.10+, standard library only. Saves raw responses and a manifest.
The organization API was found in the user's earlier NIR notebook; its current
schema and the meaning of district=2 still require live verification.
"""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = "https://dopobr.petersburgedu.ru"
DEFAULT = BASE + "/api/organization/list_odo/?district=2&is_main=true&limit=50&offset=0"


def public_url(url):
    p = urlsplit(url)
    if (p.scheme not in ("http", "https") or p.hostname != "dopobr.petersburgedu.ru"
            or p.username or p.password or p.port not in (None, 80, 443)):
        raise ValueError("Only the public Navigator host is allowed")
    if any(k.lower() in {"token", "access_token", "password", "session", "key"}
           for k, _ in parse_qsl(p.query)):
        raise ValueError("Do not supply credentials")
    return url


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        if any(x in urlsplit(newurl).path.lower() for x in ("login", "auth", "captcha")):
            raise ValueError("Authentication/challenge redirect; stopping")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.program_ids = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                p = urlsplit(urljoin(BASE, value))
                match = re.fullmatch(r"/programs/(\d+)(?:/groups)?/?", p.path)
                if p.hostname == "dopobr.petersburgedu.ru" and match:
                    self.program_ids.add(match[1])


def page_payload(body):
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Unrecognized API schema; not an empty catalogue")
    count = data.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("Missing/invalid total count")
    if any(not isinstance(row, dict) for row in data["results"]):
        raise ValueError("Non-object organization record")
    return data


def next_page(url, data):
    if "next" in data:
        return public_url(urljoin(url, data["next"])) if data["next"] else None
    p = urlsplit(url)
    params = dict(parse_qsl(p.query))
    offset = int(params.get("offset", 0)) + len(data["results"])
    if not data["results"]:
        if offset < data["count"]:
            raise ValueError("Empty page before declared total")
        return None
    if offset >= data["count"]:
        return None
    params["offset"] = str(offset)
    return urlunsplit(p._replace(query=urlencode(params)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT)
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory; existing directories are never overwritten")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--organizations", type=int, default=2)
    parser.add_argument("--programs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--delay", type=float, default=1)
    args = parser.parse_args()
    public_url(args.url)
    if not (1 <= args.pages <= 5 and 0 <= args.organizations <= 5
            and 0 <= args.programs <= 10 and 0 < args.timeout <= 30
            and args.delay >= 1):
        parser.error("Probe limits: 1–5 pages, 0–5 organizations, 0–10 programs, timeout<=30, delay>=1")
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"started_utc": datetime.now(timezone.utc).isoformat(),
                "status": "running", "complete_city_export": False,
                "district_meaning": "2 = Vasileostrovsky in earlier notebook; not live verified",
                "requests": [], "organization_records": 0, "program_links": 0}
    opener = build_opener(PublicRedirect())

    def fetch(url):
        public_url(url)
        if manifest["requests"]:
            time.sleep(args.delay)
        record = {"url": url, "retrieved_utc": datetime.now(timezone.utc).isoformat()}
        manifest["requests"].append(record)
        body = None
        try:
            req = Request(url, headers={"User-Agent": "NIR-public-data-probe/1.0",
                                       "Accept": "application/json,text/html;q=0.9"})
            with opener.open(req, timeout=args.timeout) as response:
                record.update(status=response.status, content_type=response.headers.get("Content-Type", ""),
                              final_url=response.url)
                body = response.read(10_000_001)
                if len(body) > 10_000_000:
                    raise ValueError("Response exceeds probe size limit")
        except HTTPError as exc:
            record.update(status=exc.code, error="HTTPError")
            body = exc.read(1_000_000)
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            record.update(status=None, error=type(exc).__name__, detail=str(exc))
        if body is not None:
            name = f"response-{len(manifest['requests']):03d}.bin"
            (args.output / name).write_bytes(body)
            record.update(file=name, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
        if record.get("status") != 200:
            raise RuntimeError("Public request failed; see manifest")
        return body

    records = []
    is_program_catalogue = urlsplit(args.url).path.rstrip("/") == "/api/program/list_odo"
    manifest["entity"] = "program" if is_program_catalogue else "organization"
    try:
        url = args.url
        seen = set()
        for _ in range(args.pages):
            if url in seen:
                raise ValueError("Pagination cycle")
            seen.add(url)
            data = page_payload(fetch(url))
            records.extend(data["results"])
            manifest["api_declared_count"] = data["count"]
            following = next_page(url, data)
            if not following:
                break
            url = following
        manifest["program_records" if is_program_catalogue else "organization_records"] = len(records)
        manifest["catalogue_pagination_complete"] = following is None
        (args.output / ("programs.json" if is_program_catalogue else "organizations.json")).write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        program_ids = {str(row["id"]) for row in records if str(row.get("id", "")).isdigit()} if is_program_catalogue else set()
        for org in ([] if is_program_catalogue else records[:args.organizations]):
            org_id = str(org.get("id", ""))
            if not org_id.isdigit():
                raise ValueError("Organization ID not recognized")
            html = fetch(f"{BASE}/organizations/{org_id}/programs/")
            links = Links()
            links.feed(html.decode("utf-8", errors="replace"))
            program_ids.update(links.program_ids)
        manifest["program_links"] = len(program_ids)
        for program_id in sorted(program_ids)[:args.programs]:
            fetch(f"{BASE}/programs/{program_id}/groups/")
        manifest["status"] = "probe_saved" if program_ids else "no_program_links_verified"
        # Raw organization addresses are NOT normalized into program venues.
        manifest["age_group_venue_link_verified"] = False
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        return_code = 0 if program_ids else 3
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        manifest.update(status="blocked_or_schema_unverified", error=str(exc))
        return_code = 2
    finally:
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": manifest["status"], "output": str(args.output)}, ensure_ascii=False))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
