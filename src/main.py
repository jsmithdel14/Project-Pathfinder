import pandas as pd
from candidate_generation import fetch_places_candidates
from model import SimilarityModel, CANDIDATE_FIELD_GROUPS
from pathlib import Path
from candidate_scraper import crawl_site, infer_profile
import streamlit as st

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
BASELINE_DATA_PATH = project_root / "Indiana_EXIM_Exporter_Profiles_working_v20.xlsx"

@st.cache_resource
def load_fitted_model():
    print("1. Loading verified EXIM baselines and fitting model (cached)...")
    baseline_df = pd.read_excel(BASELINE_DATA_PATH, sheet_name='Company Profiles')
    similarity_model = SimilarityModel()
    similarity_model.fit_baselines(baseline_df)
    return similarity_model

def run_pipeline(api_key: str, query: str, max_results: int):
    similarity_model = load_fitted_model()

    print("Fetching candidates from Google Places...")
    candidates_df = fetch_places_candidates(api_key, query, max_results=max_results)
    
    if candidates_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    if 'website' in candidates_df.columns:
        candidates_df['website'] = candidates_df['website'].fillna("")

    profiles = []
    
    print(f"Profiling and scraping {len(candidates_df)} candidates...")
    for _, row in candidates_df.iterrows():
        company_name = row.get("name", "Unknown")
        website = row.get("website", "")
        address = row.get("address", "Indiana") 
        
        profile_input = pd.Series({
            "Company_Name_Normalized": company_name,
            "Company_Website_Input": website,
            "City_Normalized": address, 
            "State_Normalized": "Indiana"
        })
        
        if website:
            pages = crawl_site(company=company_name, seed_url=website, max_pages=5, timeout=10, delay=0.5)
            profile_data, _ = infer_profile(profile_input, pages)
        else:
            profile_data = profile_input.to_dict()
            profile_data["Website_Check"] = "No website available to crawl"
            
        profiles.append(profile_data)
        
    scraped_df = pd.DataFrame(profiles)

    required_candidate_cols = ["Company_Name_Normalized"]
    for fields in CANDIDATE_FIELD_GROUPS.values():
        required_candidate_cols.extend(fields)
        
    for col in set(required_candidate_cols):
        if col not in scraped_df.columns:
            scraped_df[col] = ""
    
    print("Scoring candidates with the similarity model...")
    if not scraped_df.empty:
        scored_results = similarity_model.score_candidates(scraped_df, top_k=3)
        
        full_df = scored_results.sort_values(by=['Candidate', 'Rank'])

        top_1_scores = scored_results[scored_results['Rank'] == 1]
        ui_df = pd.merge(scraped_df, top_1_scores, left_on='Company_Name_Normalized', right_on='Candidate', how='left')
        
        ui_df['Score'] = ui_df['Ranking_Score'].apply(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "0.00%")
        ui_df['Best_Match'] = ui_df['Baseline_Match']
        ui_df = ui_df.sort_values(by='Ranking_Score', ascending=False)
        
        display_columns = [
            'Company_Name_Normalized', 'Score', 'Best_Match', 'Company_Website_Final'
            # 'Products_Product_Families', 'Capabilities_Manufacturing', 'Certifications_Website_Claims', 'Industries_Served'
        ]
        
        display_columns = [col for col in display_columns if col in ui_df.columns]
        display_df = ui_df[display_columns]
        
    else:
        display_df = pd.DataFrame()
        full_df = pd.DataFrame()

    return display_df, full_df
