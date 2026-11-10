"""Check selected live boards without updating published job data."""

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agencies import AGENCIES
from main import _scrape_agency


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agencies", nargs="+", help='Agency names, e.g. MBTA WMATA MTA or "LA Metro"')
    parser.add_argument("--mta-browser", action="store_true", help="Use the persistent browser directly for MTA")
    args = parser.parse_args()
    if args.mta_browser:
        os.environ["MTA_TRANSPORT"] = "browser"
    configured = {agency["agency"].casefold(): agency for agency in AGENCIES}
    unknown = [name for name in args.agencies if name.casefold() not in configured]
    if unknown:
        parser.error("Unknown agencies: " + ", ".join(unknown))
    failed = False
    for name in args.agencies:
        agency = configured[name.casefold()]
        print(f"Checking {agency['agency']} ({agency['platform']}): {agency['jobs_url']}", flush=True)
        result = _scrape_agency(agency)
        if result["error"]:
            print(f"FAILED: {result['error']}", flush=True)
            failed = True
            continue
        jobs = result["jobs"]
        print(f"Found {len(jobs)} jobs in {result['elapsed']:.1f}s", flush=True)
        if not jobs:
            print("CHECK REQUIRED: zero jobs; verify the live board before treating this as success.", flush=True)
            failed = True
        for job in jobs[:3]:
            print(f"  {job['title']}: {job['source_url']}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
