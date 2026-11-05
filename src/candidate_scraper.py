#!/usr/bin/env python3

# edit company list on line 243
"""Build reviewable company profiles from known company websites.

No search API or API key is required.

Input is hard-coded in the COMPANIES list near the top of this file.
Each entry is exactly: [company_name, website, city].

State is fixed to Indiana (IN).

Workflow:
1. Load and normalize the roster.
2. Validate each supplied website.
3. Crawl the homepage and high-value internal pages on the same registered domain.
4. Extract evidence for products, capabilities, industries, certifications, locations,
   company history, parent/DBA/former-name language, and website operating signals.
5. Write a reviewable Excel workbook with page-level evidence and a manual-review queue.

Install:
    pip install pandas openpyxl requests beautifulsoup4 lxml

Example:
    python collect_exporter_profiles_website_first.py \
        --input companies.csv \
        --output company_profiles.xlsx

Important limitations:
- This script researches the supplied official website only.
- It verifies that the website responded during the run, not the company's legal status.
- It cannot independently discover acquisitions, dissolved entities, or government records.
- Certification text is captured as website evidence, not independently authenticated.
- Review the Manual Review Queue before treating the output as final.
"""
from __future__ import annotations

import argparse
import re
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

USER_AGENT = (
    "Mozilla/5.0 (compatible; CompanyProfileResearchBot/1.0; "
    "+local-research-script)"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}

# High-value paths are crawled first. Negative terms reduce noisy or irrelevant pages.
LINK_TERMS = {
    "about": 9,
    "company": 8,
    "who-we-are": 9,
    "history": 7,
    "products": 10,
    "product": 8,
    "solutions": 8,
    "capabilities": 10,
    "manufacturing": 10,
    "engineering": 9,
    "services": 8,
    "industries": 9,
    "markets": 8,
    "quality": 10,
    "certifications": 10,
    "certification": 10,
    "accreditations": 10,
    "compliance": 8,
    "locations": 8,
    "contact": 7,
    "facilities": 9,
    "facility": 8,
    "private-label": 8,
    "contract-manufacturing": 9,
    "oem": 8,
    "testing": 8,
}

NEGATIVE_LINK_TERMS = {
    "privacy", "terms", "cookie", "login", "cart", "checkout", "account",
    "careers", "jobs", "news", "blog", "events", "press", "investors",
    "facebook", "linkedin", "instagram", "youtube", "mailto:", "tel:",
    "wp-json", "feed", "tag", "author", "search", "sitemap"
}

PRODUCT_TERMS = {
    "product", "products", "equipment", "systems", "components", "ingredients",
    "materials", "devices", "software", "platform", "solutions", "models",
    "brands", "portfolio", "offerings"
}

MANUFACTURING_TERMS = {
    "manufacturing", "manufacture", "fabrication", "fabricate", "machining",
    "assembly", "molding", "casting", "forming", "welding", "coating",
    "production", "plant", "factory", "facility", "facilities", "processing"
}

ENGINEERING_TERMS = {
    "engineering", "engineered", "design", "cad", "development", "prototype",
    "prototyping", "research and development", "r&d", "technical center"
}

CUSTOM_OEM_TERMS = {
    "custom", "customized", "oem", "private label", "contract manufacturing",
    "co-manufacturing", "co-packing", "build to print", "made to order"
}

SERVICE_TESTING_TERMS = {
    "testing", "inspection", "installation", "repair", "maintenance", "training",
    "support", "laboratory", "validation", "calibration", "quality assurance",
    "distribution", "logistics", "technical service"
}

INDUSTRY_TERMS = {
    "industries", "industry", "markets", "market", "applications", "served",
    "customers", "sectors", "aerospace", "automotive", "defense", "medical",
    "healthcare", "food", "agriculture", "construction", "energy", "industrial",
    "transportation", "government", "marine", "telecommunications"
}

IDENTITY_TERMS = {
    "parent company", "subsidiary", "division of", "doing business as", "dba",
    "formerly", "previously", "acquired by", "acquisition", "rebranded", "brand of"
}

STATUS_TERMS = {
    "closed", "ceased operations", "discontinued production", "dissolved",
    "liquidation", "no longer operating", "wind down", "winding down"
}

CERT_PATTERNS = [
    r"\bISO\s*9001(?::?\s*2015)?\b",
    r"\bISO\s*14001(?::?\s*2015)?\b",
    r"\bISO\s*13485(?::?\s*2016)?\b",
    r"\bAS\s*9100\w*\b",
    r"\bIATF\s*16949(?::?\s*2016)?\b",
    r"\bSQF(?:\s+Level\s+\d)?\b",
    r"\bENERGY\s+STAR\b",
    r"\bFDA[- ]cleared\b",
    r"\bCE[- ]marked\b",
    r"\bCLIA[- ]waived\b",
    r"\bUL\s+(?:listed|certified)\b",
    r"\bAHRI[^.;\n]{0,100}certif\w*",
    r"\bGFSI[^.;\n]{0,100}certif\w*",
]

COMMON_FILES = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip")


@dataclass
class PageRecord:
    company: str
    requested_url: str
    final_url: str
    page_title: str
    page_type: str
    http_status: int
    source_rank: int
    text_length: int
    fetched_at_utc: str
    error: str
    text: str


@dataclass
class EvidenceRecord:
    company: str
    category: str
    evidence: str
    source_url: str
    page_title: str
    source_rank: int


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_name(value: object) -> str:
    name = clean_text(value)
    return re.sub(r"\s*,\s*", ", ", name)


def canonical_key(name: str) -> str:
    value = name.lower().replace("&", "and")
    value = re.sub(
        r"\b(incorporated|corporation|company|limited|inc|corp|co|llc|ltd)\b",
        "",
        value,
    )
    return re.sub(r"[^a-z0-9]+", "", value)


def normalize_website(value: object) -> str:
    url = clean_text(value)
    if not url:
        return ""
    if not re.match(r"^https?://", url, flags=re.I):
        url = "https://" + url
    parsed = urlparse(url)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def host_key(url: str) -> str:
    host = urlparse(url).netloc.lower().split("@")[ -1].split(":")[0]
    return host.removeprefix("www.")


def same_site(candidate: str, seed: str) -> bool:
    a, b = host_key(candidate), host_key(seed)
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))


def normalize_link(url: str) -> str:
    p = urlparse(url)
    path = re.sub(r"/{2,}", "/", p.path or "/")
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", p.query, ""))


# -----------------------------------------------------------------------------
# EDIT THIS LIST ONLY
# Each company is: [company_name, website, city]
# Indiana is hard-coded for every company.
# -----------------------------------------------------------------------------
COMPANIES = [
    ["J&M Manufacturing", "https://jm-inc.com/", "Berne"],
    #["Sample Industries LLC", "https://www.sample.com", "Indianapolis"],
    #["Demo Technologies", "https://www.demo.com", "Carmel"],
]


def load_roster() -> pd.DataFrame:
    """Build the research roster from the hard-coded COMPANIES list."""
    if not isinstance(COMPANIES, list):
        raise TypeError("COMPANIES must be a list")

    rows = []
    for index, item in enumerate(COMPANIES, start=1):
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError(
                f"COMPANIES item {index} must contain exactly 3 values: "
                "[company_name, website, city]"
            )
        company_name, website, city = item
        company_name = clean_name(company_name)
        website = normalize_website(website)
        city = clean_text(city)
        if not company_name or not website or not city:
            raise ValueError(
                f"COMPANIES item {index} has a blank value; company, website, and city are required"
            )
        rows.append({
            "company_name": company_name,
            "website": website,
            "city": city,
            "Company_Name_Normalized": company_name,
            "Company_Website_Input": website,
            "City_Normalized": city,
            "State_Normalized": "Indiana",
            "Company_Key": canonical_key(company_name),
        })

    return pd.DataFrame(rows).drop_duplicates(["Company_Key", "Company_Website_Input"])

def fetch_page(session: requests.Session, url: str, timeout: int) -> tuple[requests.Response | None, str]:
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "xhtml" not in content_type:
            return None, f"Skipped non-HTML content type: {content_type or 'unknown'}"
        return response, ""
    except requests.RequestException as exc:
        return None, f"{type(exc).__name__}: {exc}"


def soup_to_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return clean_text(main.get_text(" ", strip=True))


def page_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return clean_text(soup.title.string)
    h1 = soup.find("h1")
    return clean_text(h1.get_text(" ", strip=True)) if h1 else ""


def classify_page(url: str, title: str) -> str:
    value = f"{urlparse(url).path} {title}".lower()
    best = "other"
    best_score = 0
    for term, score in LINK_TERMS.items():
        if term in value and score > best_score:
            best, best_score = term, score
    return best


def link_score(url: str, anchor: str) -> int:
    value = f"{urlparse(url).path} {anchor}".lower()
    if any(term in value for term in NEGATIVE_LINK_TERMS):
        return -100
    score = 0
    for term, points in LINK_TERMS.items():
        if term in value:
            score += points
    depth = len([x for x in urlparse(url).path.split("/") if x])
    score -= max(0, depth - 3)
    return score


def discover_links(soup: BeautifulSoup, base_url: str, seed_url: str) -> list[tuple[int, str]]:
    found: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        href = clean_text(a.get("href"))
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = normalize_link(urljoin(base_url, href))
        if not same_site(absolute, seed_url):
            continue
        if urlparse(absolute).path.lower().endswith(COMMON_FILES):
            continue
        score = link_score(absolute, clean_text(a.get_text(" ", strip=True)))
        if score > 0:
            found[absolute] = max(found.get(absolute, -999), score)
    return sorted(((score, url) for url, score in found.items()), reverse=True)


def crawl_site(
    company: str,
    seed_url: str,
    max_pages: int,
    timeout: int,
    delay: float,
) -> list[PageRecord]:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    fetched_at = datetime.now(timezone.utc).isoformat()

    queue: deque[tuple[int, str]] = deque([(100, seed_url)])
    queued = {normalize_link(seed_url)}
    visited: set[str] = set()
    pages: list[PageRecord] = []

    while queue and len(pages) < max_pages:
        score, requested = queue.popleft()
        requested = normalize_link(requested)
        if requested in visited:
            continue
        visited.add(requested)

        response, error = fetch_page(session, requested, timeout)
        if response is None:
            pages.append(
                PageRecord(company, requested, "", "", "error", 0, score, 0, fetched_at, error, "")
            )
            continue

        final_url = normalize_link(response.url)
        if not same_site(final_url, seed_url):
            pages.append(
                PageRecord(
                    company, requested, final_url, "", "redirected_external", response.status_code,
                    score, 0, fetched_at, "Redirect left supplied domain", ""
                )
            )
            continue

        soup = BeautifulSoup(response.text, "lxml")
        title = page_title(soup)
        text = soup_to_text(soup)
        ptype = "home" if len(pages) == 0 else classify_page(final_url, title)
        pages.append(
            PageRecord(
                company, requested, final_url, title, ptype, response.status_code,
                score, len(text), fetched_at, "", text
            )
        )

        if text:
            candidates = discover_links(soup, final_url, seed_url)
            combined = sorted(list(queue) + candidates, reverse=True)
            queue.clear()
            for item_score, item_url in combined:
                normalized = normalize_link(item_url)
                if normalized not in visited and normalized not in queued:
                    queue.append((item_score, normalized))
                    queued.add(normalized)

        if delay:
            time.sleep(delay)

    return pages


def split_sentences(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    return [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\s+[•|]\s+", text)
        if 35 <= len(s.strip()) <= 700
    ]


def collect_evidence(
    company: str,
    pages: Iterable[PageRecord],
    category: str,
    terms: Iterable[str],
    limit: int,
) -> list[EvidenceRecord]:
    matches: list[EvidenceRecord] = []
    seen: set[str] = set()
    for page in sorted(pages, key=lambda p: (-p.source_rank, p.final_url)):
        if page.error or not page.text:
            continue
        for sentence in split_sentences(page.text):
            lowered = sentence.lower()
            if any(term in lowered for term in terms):
                key = re.sub(r"\W+", "", lowered)[:250]
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    EvidenceRecord(
                        company, category, sentence, page.final_url, page.page_title, page.source_rank
                    )
                )
                if len(matches) >= limit:
                    return matches
    return matches


def collect_certifications(company: str, pages: Iterable[PageRecord], limit: int = 8) -> list[EvidenceRecord]:
    matches: list[EvidenceRecord] = []
    seen: set[str] = set()
    for page in sorted(pages, key=lambda p: (-p.source_rank, p.final_url)):
        if page.error or not page.text:
            continue
        for sentence in split_sentences(page.text):
            found = []
            for pattern in CERT_PATTERNS:
                found.extend(m.group(0) for m in re.finditer(pattern, sentence, flags=re.I))
            if found:
                key = sentence.lower()
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    EvidenceRecord(
                        company,
                        "certifications",
                        sentence,
                        page.final_url,
                        page.page_title,
                        page.source_rank,
                    )
                )
                if len(matches) >= limit:
                    return matches
    return matches


def summarize_evidence(records: list[EvidenceRecord], limit: int = 4) -> str:
    if not records:
        return "Not publicly verified on supplied website"
    return " | ".join(record.evidence for record in records[:limit])


def unique_urls(records: Iterable[EvidenceRecord]) -> str:
    urls: list[str] = []
    for record in records:
        if record.source_url and record.source_url not in urls:
            urls.append(record.source_url)
    return " | ".join(urls)


def infer_profile(
    row: pd.Series,
    pages: list[PageRecord],
) -> tuple[dict, list[EvidenceRecord]]:
    company = row["Company_Name_Normalized"]
    categories = {
        "products": PRODUCT_TERMS,
        "manufacturing": MANUFACTURING_TERMS,
        "engineering_design": ENGINEERING_TERMS,
        "custom_oem": CUSTOM_OEM_TERMS,
        "services_testing": SERVICE_TESTING_TERMS,
        "industries": INDUSTRY_TERMS,
        "identity": IDENTITY_TERMS,
        "status": STATUS_TERMS,
    }

    evidence: dict[str, list[EvidenceRecord]] = {
        category: collect_evidence(company, pages, category, terms, 6)
        for category, terms in categories.items()
    }
    evidence["certifications"] = collect_certifications(company, pages)
    all_evidence = [item for values in evidence.values() for item in values]

    successful = [p for p in pages if p.http_status and not p.error and p.text]
    homepage = successful[0] if successful else None
    website_status = (
        f"Website responded (HTTP {homepage.http_status}) during research run"
        if homepage
        else "Supplied website could not be successfully researched"
    )

    status_text = " ".join(r.evidence.lower() for r in evidence["status"])
    if status_text:
        operating_status = "Website contains possible inactive/closure language; manual review required"
    elif homepage:
        operating_status = "Website operational during research run; legal entity status not externally verified"
    else:
        operating_status = "Current operating status not verified"

    profile_coverage = sum(
        bool(evidence[key])
        for key in ["products", "manufacturing", "engineering_design", "custom_oem", "services_testing", "industries"]
    )
    if homepage and profile_coverage >= 4:
        confidence = "High for official-site profile; legal status not externally verified"
    elif homepage and profile_coverage >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    review_reasons: list[str] = []
    if not homepage:
        review_reasons.append("Website inaccessible or no usable HTML text")
    if len(successful) < 3:
        review_reasons.append("Fewer than three usable official-site pages crawled")
    if not evidence["products"]:
        review_reasons.append("No clear product evidence found")
    if evidence["status"]:
        review_reasons.append("Possible closure/inactive language found")
    if evidence["identity"]:
        review_reasons.append("Parent/DBA/former-name/acquisition language found")
    if evidence["certifications"]:
        review_reasons.append("Certification claims require scope/date verification")

    primary_url = homepage.final_url if homepage else row["Company_Website_Input"]
    evidence_urls = unique_urls(all_evidence)

    profile = {
        "Company_Name_Normalized": company,
        "Company_Website_Input": row["Company_Website_Input"],
        "Company_Website_Final": primary_url,
        "City": row["City_Normalized"],
        "State": row["State_Normalized"],
        "Website_Check": website_status,
        "Operating_Status": operating_status,
        "Legal_Entity_Status": "Not externally verified",
        "Parent_DBA_Former_Name_Evidence": summarize_evidence(evidence["identity"], 3),
        "Products_Product_Families": summarize_evidence(evidence["products"], 2),
        "Products_Specific_Offerings": summarize_evidence(evidence["products"], 5),
        "Capabilities_Manufacturing": summarize_evidence(evidence["manufacturing"], 4),
        "Capabilities_Engineering_Design": summarize_evidence(evidence["engineering_design"], 4),
        "Capabilities_Custom_OEM": summarize_evidence(evidence["custom_oem"], 4),
        "Capabilities_Services_Testing": summarize_evidence(evidence["services_testing"], 4),
        "Certifications_Website_Claims": summarize_evidence(evidence["certifications"], 6),
        "Certification_Scope": "Review cited page; not independently authenticated",
        "Industries_Served": summarize_evidence(evidence["industries"], 5),
        "Primary_Source_URL": primary_url,
        "Official_Source_URLs": evidence_urls,
        "Pages_Crawled": len(pages),
        "Usable_Pages": len(successful),
        "Research_Status": "Official website researched; human review required",
        "Confidence": confidence,
        "Evidence_Notes": (
            "Official-site evidence only. The script did not search government registries, "
            "news, transaction databases, or third-party sources."
        ),
        "Manual_Review_Reason": "; ".join(review_reasons) or "Quick QA recommended",
        "Research_Timestamp_UTC": datetime.now(timezone.utc).isoformat(),
    }
    return profile, all_evidence


def format_workbook(path: Path) -> None:
    workbook = load_workbook(path)
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for col in range(1, sheet.max_column + 1):
            max_len = max(
                len(str(sheet.cell(row, col).value or ""))
                for row in range(1, min(sheet.max_row, 60) + 1)
            )
            sheet.column_dimensions[get_column_letter(col)].width = min(60, max(12, max_len + 2))
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    workbook.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research hard-coded Indiana company websites without a search API.")
    parser.add_argument("--output", type=Path, default=Path("company_profiles_website_first.xlsx"))
    parser.add_argument("--max-pages", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--limit", type=int, default=0, help="Testing only; 0 processes all rows")
    args = parser.parse_args()

    roster = load_roster()
    if args.limit:
        roster = roster.head(args.limit)

    profiles: list[dict] = []
    page_rows: list[dict] = []
    evidence_rows: list[dict] = []

    for number, (_, row) in enumerate(roster.iterrows(), 1):
        company = row["Company_Name_Normalized"]
        website = row["Company_Website_Input"]
        print(f"[{number}/{len(roster)}] Crawling {company}: {website}")

        pages = crawl_site(
            company=company,
            seed_url=website,
            max_pages=max(1, args.max_pages),
            timeout=max(5, args.timeout),
            delay=max(0, args.delay),
        )
        profile, evidence = infer_profile(row, pages)
        profiles.append(profile)
        page_rows.extend(asdict(page) for page in pages)
        evidence_rows.extend(asdict(item) for item in evidence)

    profile_df = pd.DataFrame(profiles)
    page_df = pd.DataFrame(page_rows)
    evidence_df = pd.DataFrame(evidence_rows)
    review_df = profile_df[
        profile_df["Confidence"].isin(["Low", "Medium"])
        | profile_df["Manual_Review_Reason"].str.contains(
            "inaccessible|closure|Parent|DBA|former-name|acquisition",
            case=False,
            na=False,
        )
    ].copy()

    output = args.output.resolve()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        profile_df.to_excel(writer, index=False, sheet_name="Company Profiles")
        evidence_df.to_excel(writer, index=False, sheet_name="Evidence")
        page_df.to_excel(writer, index=False, sheet_name="Crawled Pages")
        review_df.to_excel(writer, index=False, sheet_name="Manual Review Queue")
        roster.to_excel(writer, index=False, sheet_name="Normalized Roster")

    format_workbook(output)
    print(
        f"Saved {output} | profiles={len(profile_df)} | "
        f"pages={len(page_df)} | evidence={len(evidence_df)} | review_queue={len(review_df)}"
    )


if __name__ == "__main__":
    main()
