"""Download the Federal Reserve's Survey of Consumer Finances summary extracts.

Two sources:
  python get_data.py            the Fed's website (federalreserve.gov)
  python get_data.py --github   a public GitHub copy of the Fed's historical
                                summary extracts (rscfpYYYY.dta, 1989-2022),
                                pinned to one commit; for when the Fed's site
                                cannot be reached

Every survey year is discovered from the Fed's SCF pages rather than typed in:
the script reads the SCF index page, follows each year's page, and downloads
the "Summary Extract Public Data" file in Stata format (scfpYYYYs.zip).

It also records, for each file, the sentence on the Fed's page that states
which year's dollars the extract uses, so plot.py can check that all years
share one constant-dollar base.

Output (in ./data):
    scfpYYYY.dta      one summary extract per survey year
    manifest.json     year -> source URL, local file, dollar-base sentence
"""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://www.federalreserve.gov/econres/"
INDEX = urljoin(BASE, "scfindex.htm")
OUT = Path(__file__).resolve().parent / "data"
GITHUB_REPO = "https://github.com/jamesohawkins/SCF-Comparison"
GITHUB_COMMIT = "29c45519a0c36c5a7739c161fc169a80cfd47c38"
GITHUB_DIR = "Raw-Data/scf_summary"
HEADERS = {"User-Agent": "Mozilla/5.0 (class assignment; SCF download)"}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    return r


def text_of(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def dollar_base_sentence(html):
    """Return the sentence(s) on a page that say which year's dollars are used."""
    hits = re.findall(r"[^.]*\b(?:19|20)\d\d dollars[^.]*\.", text_of(html))
    return [h.strip() for h in hits]


def from_github():
    """Fetch every rscfpYYYY.dta in the pinned commit; years come from the file names."""
    with tempfile.TemporaryDirectory() as tmp:
        git = ["git", "-C", tmp]
        subprocess.run(["git", "init", "-q", tmp], check=True)
        subprocess.run(git + ["remote", "add", "origin", GITHUB_REPO], check=True)
        subprocess.run(git + ["sparse-checkout", "set", GITHUB_DIR], check=True)
        subprocess.run(git + ["fetch", "-q", "--depth", "1", "--filter=blob:none",
                              "origin", GITHUB_COMMIT], check=True)
        subprocess.run(git + ["checkout", "-q", "FETCH_HEAD"], check=True)
        manifest = {}
        for f in sorted(Path(tmp, GITHUB_DIR).glob("rscfp*.dta")):
            year = re.fullmatch(r"rscfp(\d{4})\.dta", f.name).group(1)
            dest = OUT / f"scfp{year}.dta"
            shutil.copyfile(f, dest)
            print(f"{year}: {f.name}")
            manifest[year] = {
                "url": f"{GITHUB_REPO}/blob/{GITHUB_COMMIT}/{GITHUB_DIR}/{f.name}",
                "file": dest.name,
                # The Fed's historical extracts restate every year in the dollars
                # of the latest survey in the set; there is no page text to read.
                "dollar_base_text": [],
            }
    latest = max(manifest)
    for m in manifest.values():
        m["dollar_base_text"] = [f"Historical extract: {latest} dollars (latest survey in the set)."]
    return manifest


def main():
    OUT.mkdir(exist_ok=True)
    if "--github" in sys.argv:
        manifest = from_github()
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"\nSaved {len(manifest)} files to {OUT}")
        return
    index_html = get(INDEX).text

    # Each survey year has its own page, e.g. scf_2022.htm.
    year_pages = sorted(set(re.findall(r'href="([^"]*scf_(\d{4})\.htm)"', index_html)),
                        key=lambda t: t[1])
    if not year_pages:
        sys.exit(f"No year pages found on {INDEX}; the page layout may have changed.")

    manifest = {}
    for href, year in year_pages:
        page_url = urljoin(INDEX, href)
        html = get(page_url).text
        stata = re.findall(rf'href="([^"]*scfp{year}s\.zip)"', html)
        if not stata:
            print(f"{year}: no summary extract (scfp{year}s.zip) on {page_url}; skipped")
            continue
        zip_url = urljoin(page_url, stata[0])
        print(f"{year}: downloading {zip_url}")
        with zipfile.ZipFile(io.BytesIO(get(zip_url).content)) as z:
            dta = [n for n in z.namelist() if n.lower().endswith(".dta")]
            if len(dta) != 1:
                sys.exit(f"{zip_url}: expected one .dta file, found {dta}")
            dest = OUT / f"scfp{year}.dta"
            dest.write_bytes(z.read(dta[0]))
        manifest[year] = {
            "page": page_url,
            "url": zip_url,
            "file": dest.name,
            "dollar_base_text": dollar_base_sentence(html) or dollar_base_sentence(index_html),
        }

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nSaved {len(manifest)} files to {OUT}")
    for year, m in manifest.items():
        print(f"  {year}: {m['url']}")
        for s in m["dollar_base_text"]:
            print(f"        dollar base on page: {s}")


if __name__ == "__main__":
    main()
