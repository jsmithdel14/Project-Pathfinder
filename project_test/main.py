from pathlib import Path
import pandas as pd

from model import (
    SimilarityModel,
    BASELINE_FIELD_GROUPS,
    CANDIDATE_FIELD_GROUPS,
    DEFAULT_GROUP_WEIGHTS,
)

SCRIPT_DIR = Path(__file__).resolve().parent
BASELINE_DATA_PATH = SCRIPT_DIR / "Indiana_EXIM_Exporter_Profiles_working_v20.xlsx"
CANDIDATE_DATA_PATH = SCRIPT_DIR / "company_profiles_website_first.xlsx"
SHEET_NAME = "Company Profiles"
TOP_K = 3


def required_columns(field_groups, baseline=False):
    columns = ["Company_Name_Normalized"]
    for fields in field_groups.values():
        columns.extend(fields)
    if baseline:
        columns.append("Confidence")
    return list(dict.fromkeys(columns))


def load_profiles(filepath, field_groups, baseline=False):
    if not filepath.exists():
        raise FileNotFoundError(f"Excel file not found: {filepath}")
    df = pd.read_excel(filepath, sheet_name=SHEET_NAME, engine="openpyxl")
    missing = [c for c in required_columns(field_groups, baseline) if c not in df.columns]
    if missing:
        raise ValueError(f"{filepath.name} is missing required columns: {missing}")
    df = df[df["Company_Name_Normalized"].notna()].copy()
    df["Company_Name_Normalized"] = df["Company_Name_Normalized"].astype(str).str.strip()
    return df[df["Company_Name_Normalized"] != ""].reset_index(drop=True)


def fmt(value):
    return "N/A" if pd.isna(value) else f"{float(value):.4f}"


def print_results(results):
    print("\n" + "=" * 105)
    print("BGE FIELD-GROUP MATCHES - COVERAGE, RELIABILITY, AND ROLE-ADJUSTED RANKING")
    print("=" * 105)
    for candidate, group in results.groupby("Candidate", sort=False):
        print(f"\nCandidate: {candidate}\n" + "-" * 105)
        for _, r in group.sort_values("Rank").iterrows():
            if pd.isna(r["Overall_Similarity"]):
                print(f"  Candidate role: {r['Candidate_Role']}")
                print("  Insufficient comparable evidence for scoring.")
                continue
            print(f"  #{int(r['Rank'])} {r['Baseline_Match']}")
            print(f"      Ranking score:              {fmt(r['Ranking_Score'])}")
            print(f"      Raw overall similarity:     {fmt(r['Overall_Similarity'])}")
            print(f"      Evidence coverage:          {float(r['Evidence_Coverage']):.0%}")
            print(f"      Coverage factor:            {fmt(r['Coverage_Factor'])}")
            print(f"      Baseline confidence:        {r['Baseline_Confidence']}")
            print(f"      Baseline reliability:       {fmt(r['Baseline_Reliability_Factor'])}")
            print(f"      Candidate role:             {r['Candidate_Role']}")
            print(f"      Baseline role:              {r['Baseline_Role']}")
            print(f"      Role compatibility:         {fmt(r['Role_Compatibility_Factor'])}")
            print(f"      Products:                   {fmt(r['Products_Similarity'])}")
            print(f"      Capabilities:               {fmt(r['Capabilities_Similarity'])}")
            print(f"      Certifications:             {fmt(r['Certifications_Similarity'])}")
            print(f"      Industries served:          {fmt(r['Industries_Served_Similarity'])}\n")


def main():
    print("Loading baseline exporter profiles...")
    baselines = load_profiles(BASELINE_DATA_PATH, BASELINE_FIELD_GROUPS, baseline=True)
    print(f"Loaded {len(baselines)} baseline company profiles.")

    print("Loading candidate profiles...")
    candidates = load_profiles(CANDIDATE_DATA_PATH, CANDIDATE_FIELD_GROUPS)
    print(f"Loaded {len(candidates)} candidate company profiles.")

    print("\nLoading BAAI/bge-base-en-v1.5...")
    model = SimilarityModel(group_weights=DEFAULT_GROUP_WEIGHTS)
    print("Encoding baseline field groups and inferring baseline roles...")
    model.fit_baselines(baselines)
    print(f"Scoring candidates and returning top {TOP_K} role-adjusted matches...")
    results = model.score_candidates(candidates, top_k=TOP_K)
    print_results(results)

    output = SCRIPT_DIR / "candidate_similarity_results.xlsx"
    results.to_excel(output, index=False, engine="openpyxl")
    print(f"\nSaved detailed results to: {output}")


if __name__ == "__main__":
    main()
