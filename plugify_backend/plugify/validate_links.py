"""
Plugify Link Validator
----------------------
Run this on YOUR machine to validate all extension links.
Checks each Chrome Web Store link returns a valid page.

Usage:
    python validate_links.py                        # validate all
    python validate_links.py --fix                  # auto-search for broken ones
    python validate_links.py --report               # show summary only

Requirements:
    pip install requests beautifulsoup4
"""

import json
import time
import argparse
import os
import re
import requests
from datetime import datetime

DATA_PATH = os.path.join(os.path.dirname(__file__), "app", "data", "extensions.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def check_link(url: str, timeout: int = 10) -> tuple[bool, int, str]:
    """
    Check if a URL is valid and accessible.
    Returns (is_valid, status_code, reason)
    """
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True
        )
        if resp.status_code == 200:
            # Extra check — make sure it's actually an extension page
            if "chromewebstore.google.com" in url:
                if "not found" in resp.text.lower() or resp.url != url:
                    return False, resp.status_code, "Redirected or not found"
            return True, resp.status_code, "OK"
        elif resp.status_code == 404:
            return False, 404, "Extension not found — may have been removed"
        elif resp.status_code == 429:
            return None, 429, "Rate limited — try again later"
        else:
            return False, resp.status_code, f"HTTP {resp.status_code}"
    except requests.Timeout:
        return False, 0, "Timeout"
    except requests.ConnectionError as e:
        return False, 0, f"Connection error: {str(e)[:60]}"
    except Exception as e:
        return False, 0, f"Error: {str(e)[:60]}"


def search_correct_link(name: str) -> str | None:
    """
    Try to find the correct CWS link for an extension by searching.
    Uses the CWS search URL pattern.
    """
    search_url = f"https://chromewebstore.google.com/search/{requests.utils.quote(name)}"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=10)
        # Extract first extension link from results
        pattern = r'href="(https://chromewebstore\.google\.com/detail/[^"]+)"'
        matches = re.findall(pattern, resp.text)
        if matches:
            return matches[0]
    except Exception:
        pass
    return None


def validate_all(extensions: list[dict], delay: float = 1.0) -> dict:
    """
    Validate all extension links.
    Returns { valid: [], invalid: [], skipped: [] }
    """
    results = {"valid": [], "invalid": [], "skipped": [], "rate_limited": []}

    print(f"\n{'='*60}")
    print(f"Validating {len(extensions)} extension links")
    print(f"{'='*60}\n")

    for i, ext in enumerate(extensions):
        name = ext.get("name", "Unknown")
        link = ext.get("link", "")

        if not link:
            print(f"  ⚠  [{i+1}/{len(extensions)}] {name} — no link")
            results["skipped"].append(ext)
            continue

        is_valid, status, reason = check_link(link)

        if is_valid is None:  # rate limited
            print(f"  ⏸  [{i+1}/{len(extensions)}] {name} — rate limited, waiting...")
            results["rate_limited"].append(ext)
            time.sleep(10)  # wait longer
        elif is_valid:
            print(f"  ✅ [{i+1}/{len(extensions)}] {name}")
            results["valid"].append(ext)
        else:
            print(f"  ❌ [{i+1}/{len(extensions)}] {name} — {reason}")
            results["invalid"].append({**ext, "_error": reason})

        # Polite delay between requests
        time.sleep(delay)

    return results


def print_report(results: dict):
    total = sum(len(v) for v in results.values())
    valid = len(results["valid"])
    invalid = len(results["invalid"])
    skipped = len(results["skipped"])

    print(f"\n{'='*60}")
    print(f"VALIDATION REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"  Total checked : {total}")
    print(f"  ✅ Valid       : {valid} ({valid/total*100:.1f}%)")
    print(f"  ❌ Invalid     : {invalid} ({invalid/total*100:.1f}%)")
    print(f"  ⚠  Skipped    : {skipped}")
    print(f"{'='*60}")

    if results["invalid"]:
        print(f"\nInvalid extensions:")
        for ext in results["invalid"]:
            print(f"  • {ext['name']} — {ext.get('_error','?')}")
            print(f"    {ext.get('link','')}")


def save_valid_only(results: dict):
    """Save only valid extensions back to extensions.json"""
    valid = results["valid"]

    # Backup first
    backup_path = DATA_PATH.replace(".json", "_backup.json")
    with open(DATA_PATH, encoding="utf-8") as f:
        original = json.load(f)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(original, f, indent=2, ensure_ascii=False)
    print(f"\nBackup saved to {backup_path}")

    # Save valid only
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(valid, f, indent=2, ensure_ascii=False)

    # Delete stale embeddings
    emb_path = DATA_PATH.replace("extensions.json", "embeddings.npy")
    if os.path.exists(emb_path):
        os.remove(emb_path)
        print("Deleted stale embeddings.npy")

    removed = len(original) - len(valid)
    print(f"\n✅ Saved {len(valid)} valid extensions ({removed} removed)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plugify Link Validator")
    parser.add_argument("--fix", action="store_true",
                        help="Remove invalid links and save cleaned dataset")
    parser.add_argument("--report", action="store_true",
                        help="Show report only without saving")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between requests in seconds (default: 1.0)")
    args = parser.parse_args()

    # Load dataset
    with open(DATA_PATH, encoding="utf-8") as f:
        extensions = json.load(f)

    # Validate
    results = validate_all(extensions, delay=args.delay)

    # Report
    print_report(results)

    # Save if requested
    if args.fix and not args.report:
        save_valid_only(results)
    elif not args.fix:
        print("\nRun with --fix to remove invalid links and save cleaned dataset")
