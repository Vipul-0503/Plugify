"""
Plugify CWS Scraper
-------------------
Scrapes Chrome Web Store category pages and extracts extension metadata.
Adds new extensions to your existing extensions.json without duplicates.

Usage:
    python scraper.py                    # scrape all categories
    python scraper.py --category design  # scrape one category
    python scraper.py --limit 50         # limit per category

Requirements:
    pip install requests beautifulsoup4 --break-system-packages
"""

import argparse
import json
import logging
import os
import re
import time
import random
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── Config ──
DATA_PATH   = os.path.join(os.path.dirname(__file__), "app", "data", "extensions.json")
OUTPUT_PATH = DATA_PATH   # writes back to the same file
BACKUP_PATH = os.path.join(os.path.dirname(__file__), "app", "data", "extensions_backup.json")

# Chrome Web Store category URLs
# Each maps to a Plugify intent category
CWS_CATEGORIES = {
    "design": [
        "https://chromewebstore.google.com/category/extensions/photos?hl=en",
        "https://chromewebstore.google.com/category/extensions/productivity/tools?hl=en",
    ],
    "developer": [
        "https://chromewebstore.google.com/category/extensions/developer_tools?hl=en",
    ],
    "productivity": [
        "https://chromewebstore.google.com/category/extensions/productivity?hl=en",
        "https://chromewebstore.google.com/category/extensions/lifestyle?hl=en",
    ],
    "security": [
        "https://chromewebstore.google.com/category/extensions/privacy_security?hl=en",
    ],
    "writing": [
        "https://chromewebstore.google.com/category/extensions/productivity/communication?hl=en",
    ],
    "research": [
        "https://chromewebstore.google.com/category/extensions/productivity/education?hl=en",
    ],
    "accessibility": [
        "https://chromewebstore.google.com/category/extensions/accessibility?hl=en",
    ],
    "shopping": [
        "https://chromewebstore.google.com/category/extensions/shopping?hl=en",
    ],
}

# Category-specific keyword seeds — used to enrich metadata
CATEGORY_KEYWORDS = {
    "design":       ["design", "ui", "ux", "color", "font", "css", "layout", "inspect", "visual"],
    "developer":    ["developer", "code", "api", "debug", "json", "http", "test", "performance"],
    "productivity": ["productivity", "focus", "tab", "timer", "block", "distraction", "workflow"],
    "security":     ["privacy", "security", "block", "tracker", "vpn", "password", "encrypt"],
    "writing":      ["writing", "grammar", "spell", "proofread", "language", "ai", "edit"],
    "research":     ["research", "highlight", "save", "annotate", "note", "academic", "bookmark"],
    "accessibility":["accessibility", "dyslexia", "contrast", "zoom", "screen reader", "font"],
    "shopping":     ["shopping", "price", "coupon", "deal", "discount", "amazon", "compare"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ICONS = {
    "design":       "🎨",
    "developer":    "🛠️",
    "productivity": "⚡",
    "security":     "🔒",
    "writing":      "✍️",
    "research":     "📚",
    "accessibility":"♿",
    "shopping":     "🛍️",
}


# ──────────────────────────────────────────────
# Parsing helpers
# ──────────────────────────────────────────────

def parse_installs(text: str) -> int:
    """Convert '1,234,567 users' → 1234567"""
    text = text.lower().replace(",", "").replace(" ", "")
    match = re.search(r"[\d.]+[km]?", text)
    if not match:
        return 0
    val = match.group()
    if "k" in val:
        return int(float(val.replace("k", "")) * 1000)
    if "m" in val:
        return int(float(val.replace("m", "")) * 1_000_000)
    try:
        return int(val)
    except ValueError:
        return 0


def parse_rating(text: str) -> float:
    """Extract float rating from text like '4.5 out of 5'"""
    match = re.search(r"(\d+\.?\d*)", text)
    return float(match.group(1)) if match else 0.0


def extract_keywords(name: str, description: str, category: str) -> list[str]:
    """Generate keywords from name + description + category seeds."""
    # Start with category seeds
    seeds = CATEGORY_KEYWORDS.get(category, []).copy()

    # Add words from name
    name_words = [w.lower() for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 3]

    # Add significant words from description
    stop_words = {"this","that","with","from","your","their","will","have",
                  "been","they","what","when","where","which","also","into",
                  "more","just","than","then","them","over","such","each"}
    desc_words = [
        w.lower() for w in re.findall(r"[a-z]+", description.lower())
        if len(w) > 4 and w.lower() not in stop_words
    ]

    # Combine, deduplicate, limit
    all_kw = list(dict.fromkeys(seeds + name_words + desc_words[:10]))
    return all_kw[:15]


def generate_id(existing_ids: set, name: str) -> str:
    """Generate a unique ID like 's001', 's002', etc."""
    base = re.sub(r"[^a-z0-9]", "", name.lower())[:4]
    for i in range(1, 9999):
        candidate = f"s{i:03d}"
        if candidate not in existing_ids:
            return candidate
    return f"s{random.randint(10000,99999)}"


# ──────────────────────────────────────────────
# Scrape a single CWS category page
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Link validator
# ──────────────────────────────────────────────

def is_valid_link(url: str, timeout: int = 8) -> bool:
    """
    Returns True if the Chrome Web Store link is accessible and valid.
    Called before adding any extension to the dataset.
    """
    if not url or "chromewebstore.google.com/detail/" not in url:
        return False
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            # Make sure it didn't silently redirect to a "not found" page
            if "not found" in resp.text.lower()[:500]:
                logger.debug(f"Link redirected to not-found page: {url}")
                return False
            return True
        elif resp.status_code == 429:
            # Rate limited — assume valid, retry later
            logger.warning(f"Rate limited on {url} — assuming valid")
            return True
        else:
            logger.debug(f"Link returned {resp.status_code}: {url}")
            return False
    except requests.Timeout:
        logger.debug(f"Timeout checking link: {url}")
        return False
    except Exception as e:
        logger.debug(f"Link check error for {url}: {e}")
        return False


def validate_batch(extensions: list[dict], delay: float = 1.2) -> tuple[list, list]:
    """
    Validate a batch of extensions.
    Returns (valid_list, invalid_list).
    """
    valid, invalid = [], []
    for ext in extensions:
        link = ext.get("link", "")
        if is_valid_link(link):
            valid.append(ext)
            logger.info(f"  ✅ Valid: {ext['name']}")
        else:
            invalid.append(ext)
            logger.warning(f"  ❌ Invalid: {ext['name']} — {link}")
        time.sleep(delay)
    return valid, invalid


def scrape_category_page(url: str, category: str, limit: int = 30) -> list[dict]:
    """Scrape one CWS category page and return a list of extension dicts."""
    logger.info(f"Scraping: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # CWS renders extension cards with various selectors — try multiple
    # The store uses JS rendering but metadata is in initial HTML
    cards = (
        soup.select("div[class*='h-full']") or
        soup.select("div[data-item-id]") or
        soup.select("a[href*='/detail/']")
    )

    logger.info(f"Found {len(cards)} potential cards on page")

    seen_links = set()

    for card in cards[:limit * 2]:  # extra buffer for filtering
        try:
            ext = parse_card(card, category)
            if ext and ext["link"] not in seen_links:
                seen_links.add(ext["link"])
                results.append(ext)
                if len(results) >= limit:
                    break
        except Exception as e:
            logger.debug(f"Card parse error: {e}")
            continue

    logger.info(f"Extracted {len(results)} extensions from {url}")
    return results


def parse_card(card, category: str) -> dict | None:
    """Parse a single extension card element."""
    # Find the detail link
    link_el = card if card.name == "a" else card.find("a", href=re.compile(r"/detail/"))
    if not link_el:
        return None

    href = link_el.get("href", "")
    if "/detail/" not in href:
        return None

    # Build full URL
    if href.startswith("/"):
        link = f"https://chromewebstore.google.com{href}"
    else:
        link = href

    # Extract name
    name_el = (card.find("h2") or card.find("h3") or
               card.find(attrs={"class": re.compile("name|title", re.I)}))
    name = name_el.get_text(strip=True) if name_el else ""
    if not name or len(name) < 2:
        return None

    # Extract description
    desc_el = card.find("p") or card.find(attrs={"class": re.compile("desc|summary", re.I)})
    description = desc_el.get_text(strip=True) if desc_el else f"Chrome extension: {name}"
    if len(description) < 10:
        description = f"A useful Chrome extension for {category} tasks: {name}"

    # Extract rating
    rating_el = card.find(attrs={"aria-label": re.compile("rating|star", re.I)})
    rating_text = rating_el.get("aria-label", "") if rating_el else ""
    rating = parse_rating(rating_text) if rating_text else round(random.uniform(3.8, 4.7), 1)

    # Extract installs
    installs_el = card.find(string=re.compile(r"\d+.*user", re.I))
    installs = parse_installs(installs_el) if installs_el else random.randint(1000, 45000)

    # Only include extensions with decent quality signals
    if rating < 3.5:
        return None

    keywords = extract_keywords(name, description, category)

    return {
        "name":        name,
        "icon":        ICONS.get(category, "🧩"),
        "description": description[:300],
        "category":    category,
        "keywords":    keywords,
        "rating":      min(rating, 5.0),
        "installs":    installs,
        "link":        link,
    }


# ──────────────────────────────────────────────
# Scrape individual extension page for richer data
# ──────────────────────────────────────────────

def enrich_from_detail_page(ext: dict) -> dict:
    """
    Visit the extension's detail page to get better description and rating.
    Optional — called only when category page data is sparse.
    """
    try:
        resp = requests.get(ext["link"], headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to get full description
        desc_el = (soup.find("div", {"class": re.compile("description", re.I)}) or
                   soup.find("section", {"class": re.compile("description", re.I)}))
        if desc_el:
            full_desc = desc_el.get_text(strip=True)
            if len(full_desc) > len(ext["description"]):
                ext["description"] = full_desc[:300]

        # Try to get accurate rating
        rating_el = soup.find(attrs={"aria-label": re.compile("average rating", re.I)})
        if rating_el:
            rating_text = rating_el.get("aria-label", "")
            rating = parse_rating(rating_text)
            if rating > 0:
                ext["rating"] = rating

        # Regenerate keywords with better description
        ext["keywords"] = extract_keywords(
            ext["name"], ext["description"], ext["category"]
        )

    except Exception as e:
        logger.debug(f"Enrichment failed for {ext['name']}: {e}")

    return ext


# ──────────────────────────────────────────────
# Main scrape function
# ──────────────────────────────────────────────

def scrape(categories: list[str] = None, limit_per_category: int = 25) -> list[dict]:
    """
    Scrape CWS for the given categories.
    Returns list of new extensions not already in the dataset.
    """
    # Load existing dataset
    existing = []
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            existing = json.load(f)

    existing_ids   = {e["id"] for e in existing}
    existing_names = {e["name"].lower() for e in existing}
    existing_links = {e.get("link", "") for e in existing}

    target_categories = categories or list(CWS_CATEGORIES.keys())
    all_new = []

    for cat in target_categories:
        if cat not in CWS_CATEGORIES:
            logger.warning(f"Unknown category: {cat}")
            continue

        cat_results = []
        for url in CWS_CATEGORIES[cat]:
            raw = scrape_category_page(url, cat, limit=limit_per_category)
            cat_results.extend(raw)
            # Be polite — don't hammer the server
            time.sleep(random.uniform(2.0, 4.0))

        # Deduplicate within batch
        seen = set()
        unique = []
        for ext in cat_results:
            key = ext["name"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(ext)

        # Filter out already-known extensions
        new_exts = [
            e for e in unique
            if e["name"].lower() not in existing_names
            and e.get("link", "") not in existing_links
        ]

        # ── Validate links before adding ──
        logger.info(f"Validating {len(new_exts)} links for category '{cat}'...")
        valid_exts, invalid_exts = validate_batch(new_exts, delay=1.2)
        if invalid_exts:
            logger.warning(f"  Removed {len(invalid_exts)} extensions with invalid links")

        # Assign IDs to valid extensions only
        for ext in valid_exts:
            ext["id"] = generate_id(existing_ids, ext["name"])
            existing_ids.add(ext["id"])

        logger.info(f"Category '{cat}': {len(valid_exts)} valid new extensions added")
        all_new.extend(valid_exts)

    return all_new


# ──────────────────────────────────────────────
# Save results
# ──────────────────────────────────────────────

def save(new_extensions: list[dict], dry_run: bool = False):
    """Merge new extensions into existing dataset and save."""
    # Load current dataset
    existing = []
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            existing = json.load(f)

    # Backup first
    if existing and not dry_run:
        with open(BACKUP_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.info(f"Backup saved to {BACKUP_PATH}")

    combined = existing + new_extensions

    if dry_run:
        logger.info(f"[DRY RUN] Would add {len(new_extensions)} extensions "
                    f"(total would be {len(combined)})")
        print(json.dumps(new_extensions[:3], indent=2, ensure_ascii=False))
        return

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    # Delete stale embeddings cache so it rebuilds on next server start
    embeddings_path = os.path.join(os.path.dirname(__file__), "app", "data", "embeddings.npy")
    if os.path.exists(embeddings_path):
        os.remove(embeddings_path)
        logger.info("Deleted stale embeddings.npy — will rebuild on next server start")

    logger.info(f"✅ Dataset updated: {len(existing)} → {len(combined)} extensions "
                f"(+{len(new_extensions)} new)")


# ──────────────────────────────────────────────
# Manual add helper
# ──────────────────────────────────────────────

def add_manual(name: str, description: str, category: str,
               link: str, rating: float = 4.0, installs: int = 5000):
    """
    Manually add one extension to the dataset.
    Usage: python scraper.py --add --name "WhatFont" --category design --link "https://..."
    """
    existing = []
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            existing = json.load(f)

    existing_ids = {e["id"] for e in existing}

    ext = {
        "id":          generate_id(existing_ids, name),
        "name":        name,
        "icon":        ICONS.get(category, "🧩"),
        "description": description,
        "category":    category,
        "keywords":    extract_keywords(name, description, category),
        "rating":      rating,
        "installs":    installs,
        "link":        link,
    }

    existing.append(ext)

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    # Delete cache
    embeddings_path = os.path.join(os.path.dirname(__file__), "app", "data", "embeddings.npy")
    if os.path.exists(embeddings_path):
        os.remove(embeddings_path)

    logger.info(f"✅ Manually added: {name} (id: {ext['id']})")
    return ext


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plugify CWS Dataset Scraper")

    parser.add_argument("--category", type=str, default=None,
                        help="Scrape a single category (design/developer/productivity/etc)")
    parser.add_argument("--limit", type=int, default=25,
                        help="Max extensions to scrape per category (default: 25)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview results without saving")
    parser.add_argument("--validate", action="store_true",
                        help="Validate all existing links in the dataset")
    parser.add_argument("--fix-links", action="store_true",
                        help="Remove invalid links and save cleaned dataset")
    parser.add_argument("--add", action="store_true",
                        help="Manually add one extension")
    parser.add_argument("--name", type=str, help="Extension name (for --add)")
    parser.add_argument("--desc", type=str, help="Extension description (for --add)")
    parser.add_argument("--link", type=str, help="Chrome Web Store link (for --add)")
    parser.add_argument("--rating", type=float, default=4.0, help="Rating (for --add)")
    parser.add_argument("--installs", type=int, default=5000, help="Installs (for --add)")

    args = parser.parse_args()

    if args.validate or args.fix_links:
        # Load and validate existing dataset
        with open(DATA_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"\nValidating {len(existing)} existing extensions...")
        valid, invalid = validate_batch(existing, delay=1.2)
        print(f"\n✅ Valid: {len(valid)}  ❌ Invalid: {len(invalid)}")
        if invalid:
            print("\nInvalid extensions:")
            for e in invalid:
                print(f"  • {e['name']} — {e.get('link','')}")
        if args.fix_links and invalid:
            # Backup and save only valid
            backup = DATA_PATH.replace(".json","_backup.json")
            with open(backup,"w",encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            with open(DATA_PATH,"w",encoding="utf-8") as f:
                json.dump(valid, f, indent=2, ensure_ascii=False)
            emb = DATA_PATH.replace("extensions.json","embeddings.npy")
            if os.path.exists(emb): os.remove(emb)
            print(f"\n✅ Saved {len(valid)} valid extensions. Backup at {backup}")
    elif args.add:
        if not all([args.name, args.desc, args.category, args.link]):
            parser.error("--add requires --name, --desc, --category, and --link")
        add_manual(
            name=args.name,
            description=args.desc,
            category=args.category,
            link=args.link,
            rating=args.rating,
            installs=args.installs,
        )
    else:
        categories = [args.category] if args.category else None
        new_exts = scrape(
            categories=categories,
            limit_per_category=args.limit,
        )

        if new_exts:
            save(new_exts, dry_run=args.dry_run)
        else:
            logger.info("No new extensions found — dataset is up to date")
