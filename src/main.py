from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse
import pandas as pd
import streamlit as st

from candidate_generation import fetch_places_candidates
from candidate_scraper import crawl_site, infer_profile
from model import CANDIDATE_FIELD_GROUPS, SimilarityModel

# Readiness & scoring helpers
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
BASELINE_DATA_PATH = project_root / "Indiana_EXIM_Exporter_Profiles_working_v20.xlsx"

EXPORT_KEYWORD_LABELS = {
    r"\bexport(?:s|ed|ing|er|ers)?\b": "Export / Exporter",
    r"\binternational(?:ly)?\b": "International",
    r"\bworldwide\b": "Worldwide",
    r"\bglobal(?:ly)?\b": "Global",
    r"\boverseas\b": "Overseas",
    r"\bforeign markets?\b": "Foreign Markets",
    r"\bdistributors? worldwide\b": "Worldwide Distributors",
    r"\bglobal footprint\b": "Global Footprint",
    r"\bcustoms\b": "Customs",
    r"\bincoterms\b": "Incoterms",
    r"\bce[- ]mark(?:ed|ing)?\b": "CE Mark",
    r"\bitar\b": "ITAR Compliance",
    r"\bfreight forwarding\b": "Freight Forwarding",
}

OEM_KEYWORDS = [
    r"\boem\b",
    r"\bcontract manufactur\w+\b",
    r"\bprivate label\b",
    r"\bbuild to print\b",
    r"\bmade to order\b",
    r"\bcustom fabricat\w+\b",
    r"\bco-manufactur\w+\b",
]

UNVERIFIED_PLACEHOLDER = "not publicly verified on supplied website"

def safe_clean_str(val: Any) -> str:
    """Safely converts pandas values to string without turning NaN into 'nan'."""
    if pd.isna(val) or val is None:
        return ""
    text = str(val).strip().lower()
    return "" if text == "nan" else text

def get_root_domain(url: str) -> str:
    """Extract registered domain (e.g., 'chick-fil-a.com') to catch duplicate store branches."""
    if not url:
        return ""
    netloc = urlparse(url if "://" in url else f"https://{url}").netloc.lower().split("@")[-1].split(":")[0]
    netloc = netloc.removeprefix("www.")
    parts = netloc.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else netloc


def calibrate_similarity(
    raw_similarity: float,
    floor: float = 0.54,
    ceiling: float = 0.82,
) -> float:
    """Rescales compressed dense cosine similarity into a normalized 0.0 - 1.0 interval."""
    if pd.isna(raw_similarity) or raw_similarity <= floor:
        return 0.0
    if raw_similarity >= ceiling:
        return 1.0
    return (raw_similarity - floor) / (ceiling - floor)


def evaluate_export_readiness(
    row: Mapping[str, Any],
    raw_score_col: str = "Ranking_Score",
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Calculates a composite Export Readiness Index (0 - 100) and component breakdown."""
    if weights is None:
        weights = {
            "similarity": 40.0,
            "export_intent": 25.0,
            "certifications": 20.0,
            "oem_capability": 15.0,
        }

    # Calibrated Similarity (0 to 40 pts)
    raw_score = float(row.get(raw_score_col, 0.0) or 0.0)
    norm_sim = calibrate_similarity(raw_score)
    sim_pts = round(norm_sim * weights["similarity"], 2)
    evidence_fields = [
        safe_clean_str(row.get("Products_Product_Families", "")),
        safe_clean_str(row.get("Products_Specific_Offerings", "")),
        safe_clean_str(row.get("Capabilities_Manufacturing", "")),
        safe_clean_str(row.get("Capabilities_Custom_OEM", "")),
        safe_clean_str(row.get("Capabilities_Engineering_Design", "")),
        safe_clean_str(row.get("Industries_Served", "")),
        safe_clean_str(row.get("Parent_DBA_Former_Name_Evidence", "")),
    ]
    searchable_text = " ".join(evidence_fields)

    # Export Intent Signals (0 to 25 pts)
    export_matches = set()
    for pattern, label in EXPORT_KEYWORD_LABELS.items():
        if re.search(pattern, searchable_text, flags=re.I):
            export_matches.add(label)

    if len(export_matches) >= 3:
        export_pts = weights["export_intent"]
    elif len(export_matches) == 2:
        export_pts = round(weights["export_intent"] * 0.70, 2)
    elif len(export_matches) == 1:
        export_pts = round(weights["export_intent"] * 0.40, 2)
    else:
        export_pts = 0.0

    # Certifications & Quality Assurance (0 to 20 pts)
    cert_text = safe_clean_str(row.get("Certifications_Website_Claims", ""))
    if not cert_text or UNVERIFIED_PLACEHOLDER in cert_text:
        cert_pts = 0.0
    else:
        cert_count = len([s for s in cert_text.split(" | ") if s.strip()])
        cert_pts = weights["certifications"] if cert_count >= 2 else round(weights["certifications"] * 0.60, 2)

    # B2B OEM / Manufacturing Capability (0 to 15 pts)
    oem_text = safe_clean_str(row.get("Capabilities_Custom_OEM", ""))
    mfg_text = safe_clean_str(row.get("Capabilities_Manufacturing", ""))
    combined_mfg = f"{oem_text} {mfg_text}"

    has_oem_text = bool(oem_text and UNVERIFIED_PLACEHOLDER not in oem_text)
    keyword_hits = sum(bool(re.search(pat, combined_mfg, flags=re.I)) for pat in OEM_KEYWORDS)

    if has_oem_text or keyword_hits >= 2:
        oem_pts = weights["oem_capability"]
    elif keyword_hits == 1:
        oem_pts = round(weights["oem_capability"] * 0.50, 2)
    else:
        oem_pts = 0.0

    total_score = round(sim_pts + export_pts + cert_pts + oem_pts, 2)

    if total_score >= 70.0:
        tier = "High Readiness"
    elif total_score >= 45.0:
        tier = "Developing / Moderate"
    else:
        tier = "Early / Unverified"

    return {
        "Readiness_Score": total_score,
        "Readiness_Tier": tier,
        "Sim_Points": sim_pts,
        "Export_Points": export_pts,
        "Cert_Points": cert_pts,
        "OEM_Points": oem_pts,
        "Export_Signals_Found": ", ".join(sorted(export_matches)) if export_matches else "None",
    }


# Model loader and pipeline
@st.cache_resource
def load_fitted_model():
    """Load and fit the similarity model with baseline data."""
    baseline_df = pd.read_excel(BASELINE_DATA_PATH, sheet_name="Company Profiles")
    similarity_model = SimilarityModel()
    similarity_model.fit_baselines(baseline_df)
    return similarity_model


def run_pipeline(api_key: str, query: str, max_results: int):
    """Run the full candidate generation, scraping, and composite scoring pipeline."""
    similarity_model = load_fitted_model()

    candidates_df = fetch_places_candidates(api_key, query, max_results=max_results)
    if candidates_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    if "website" not in candidates_df.columns:
        candidates_df["website"] = ""
    else:
        candidates_df["website"] = candidates_df["website"].fillna("")

    candidates_df["root_domain"] = candidates_df["website"].apply(get_root_domain)

    # Deduplicate locations
    candidates_df = candidates_df.drop_duplicates(subset=["name"]).copy()
    has_site = candidates_df["root_domain"] != ""
    candidates_df = pd.concat([
        candidates_df[has_site].drop_duplicates(subset=["root_domain"]),
        candidates_df[~has_site]
    ], ignore_index=True)

    profiles = []

    for _, row in candidates_df.iterrows():
        company_name = row.get("name", "Unknown")
        website = row.get("website", "")
        address = row.get("address", "Indiana")

        if website and not website.startswith(("http://", "https://")):
            website = "https://" + website

        profile_input = {
            "Company_Name_Normalized": company_name,
            "Company_Website_Input": website,
            "City_Normalized": address,
            "State_Normalized": "Indiana",
        }

        if website:
            pages = crawl_site(company=company_name, seed_url=website, max_pages=5, timeout=10, delay=0.5)
            profile_data, _ = infer_profile(profile_input, pages)
        else:
            profile_data = dict(profile_input)
            profile_data["Website_Check"] = "No website available to crawl"
            profile_data["Company_Website_Final"] = ""

        profiles.append(profile_data)

    scraped_df = pd.DataFrame(profiles)

    required_candidate_cols = ["Company_Name_Normalized"]
    for fields in CANDIDATE_FIELD_GROUPS.values():
        required_candidate_cols.extend(fields)

    for col in set(required_candidate_cols):
        if col not in scraped_df.columns:
            scraped_df[col] = ""

    if not scraped_df.empty:
        scored_results = similarity_model.score_candidates(scraped_df, top_k=3)
        top_1_scores = scored_results[scored_results["Rank"] == 1].drop_duplicates(subset=["Candidate"])

        ui_df = pd.merge(
            scraped_df,
            top_1_scores,
            left_on="Company_Name_Normalized",
            right_on="Candidate",
            how="left",
        )

        # Multi-factor readiness calculation
        readiness_metrics = ui_df.apply(evaluate_export_readiness, axis=1, result_type="expand")
        ui_df = pd.concat([ui_df, readiness_metrics], axis=1)

        ui_df["Raw_Similarity"] = ui_df["Ranking_Score"].apply(lambda x: f"{x * 100:.1f}%" if pd.notna(x) else "0.0%")
        ui_df["Composite_Readiness"] = ui_df["Readiness_Score"].apply(lambda x: f"{x:.1f} / 100")
        ui_df["Score"] = ui_df["Raw_Similarity"]
        ui_df["Best_Match"] = ui_df["Baseline_Match"]
        ui_df = ui_df.sort_values(by="Readiness_Score", ascending=False)

        score_cols = ui_df[["Company_Name_Normalized", "Readiness_Score", "Readiness_Tier"]].drop_duplicates(
            subset=["Company_Name_Normalized"]
        )
        full_df = pd.merge(
            scored_results,
            score_cols,
            left_on="Candidate",
            right_on="Company_Name_Normalized",
            how="left",
        ).drop(columns=["Company_Name_Normalized"])

        full_df = full_df.sort_values(
            by=["Candidate", "Rank", "Readiness_Score"],
            ascending=[True, True, False],
        )

        display_columns = [
            "Company_Name_Normalized",
            "Composite_Readiness",
            "Readiness_Tier",
            "Best_Match",
            "Raw_Similarity",
            "Export_Signals_Found",
            "Company_Website_Final",
        ]
        display_columns = [col for col in display_columns if col in ui_df.columns]
        display_df = ui_df[display_columns].drop_duplicates(subset=["Company_Name_Normalized"])
    else:
        display_df = pd.DataFrame()
        full_df = pd.DataFrame()

    return display_df, full_df
