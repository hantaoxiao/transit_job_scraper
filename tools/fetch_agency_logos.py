from pathlib import Path
from time import sleep
from urllib.parse import quote

import requests


OUT_DIR = Path("site/assets/agency-logos")
COMMONS_REDIRECT = "https://commons.wikimedia.org/wiki/Special:Redirect/file/"
COMMONS_THUMBNAIL_WIDTH = 420
HEADERS = {"User-Agent": "Mozilla/5.0"}


COMMONS_FILES = {
    "ac-transit": "AC Transit logo (2014+) cropped.svg",
    "bart": "Bart-logo.svg",
    "cta": "Chicago Transit Authority Logo.svg",
    "honolulu-dts": "TheBus logo.svg",
    "la-metro": "LAMetroLogo.svg",
    "marta": "Logo of the Metropolitan Atlanta Rapid Transit Authority.svg",
    "mbta": "MBTA Primary Logo.svg",
    "mta": "MTA NYC logo.svg",
    "nj-transit": "New Jersey Transit Logo.svg",
    "rtd-denver": "Regional Transportation District logo.svg",
    "septa": "SEPTA text.svg",
    "sfmta": "Muni worm logo.svg",
    "sound-transit": "Sound Transit logo.svg",
    "trimet": "Trimet logo.svg",
    "wmata": "WMATA Logo 2025.svg",
}


DIRECT_URLS = {
    "king-county-metro": "https://cdn.kingcounty.gov/-/media/king-county/depts/metro/logo-art/metro/metro_logotype_992x205.png",
    "mta": "https://upload.wikimedia.org/wikipedia/commons/3/3c/MTA_NYC_logo.svg",
    "nj-transit": "https://www.njtransit.com/assets/njt_thumbnail_logo.png",
    "rtc-transit": "https://upload.wikimedia.org/wikipedia/en/thumb/8/88/RTC_white_logo.png/250px-RTC_white_logo.png",
    "sound-transit": "https://upload.wikimedia.org/wikipedia/commons/a/a5/Sound_Transit_logo.svg",
    "wmata": "https://upload.wikimedia.org/wikipedia/commons/5/5a/WMATA_Logo_2025.svg",
}


def extension_for(url, response):
    content_type = response.headers.get("content-type", "")
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    if "svg" in content_type:
        return ".svg"
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    return ".png"


def download(slug, url):
    for attempt in range(4):
        response = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        if response.status_code != 429:
            response.raise_for_status()
            ext = extension_for(response.url, response)
            path = OUT_DIR / f"{slug}{ext}"
            path.write_bytes(response.content)
            return path
        sleep(2 + attempt * 2)
    response.raise_for_status()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for slug, filename in COMMONS_FILES.items():
        path = download(slug, f"{COMMONS_REDIRECT}{quote(filename)}?width={COMMONS_THUMBNAIL_WIDTH}")
        print(f"{slug}: {filename} -> {path}")
        sleep(0.8)
    for slug, url in DIRECT_URLS.items():
        path = download(slug, url)
        print(f"{slug}: direct -> {path}")


if __name__ == "__main__":
    main()
