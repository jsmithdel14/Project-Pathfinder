import os
import os
import pandas as pd
from candidate_generation import fetch_places_candidates
from model import SimilarityModel
from pathlib import Path
from candidate_scraper import crawl_site, infer_profile

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
BASELINE_DATA_PATH = project_root / "Indiana_EXIM_Exporter_Profiles_working_v20.xlsx"

def load_dynamic_baselines(filepath: str) -> dict:
    """Reads the Excel file and combines profile columns into a single text block per company."""
    df = pd.read_excel(filepath, sheet_name='Company Profiles')
    
    # Filter to only verified exporters with a website
    valid_df = df[
        (df['Exporter_Verification'].str.contains('verified|supported', case=False, na=False)) & 
        (df['Company_Website'].notna())
    ]
    
    baselines = {}
    for _, row in valid_df.iterrows():
        name = row['Company_Name_Normalized']
        # Combine the high-value text fields to build a robust baseline signature
        text_components = [
            str(row.get('Products_Product_Families', '')),
            str(row.get('Capabilities_Manufacturing', '')),
            str(row.get('Capabilities_Engineering_Design', '')),
            str(row.get('Industries_Served', ''))
        ]
        
        # Clean up empty strings or 'nan' values from pandas
        clean_text = " ".join([t for t in text_components if t.strip() and str(t).lower() != 'nan'])
        if clean_text:
            baselines[name] = clean_text
            
    return baselines

def run_pipeline(api_key: str, query: str, max_results: int) -> pd.DataFrame:
    print("1. Loading verified EXIM baselines...")
    baseline_dict = load_dynamic_baselines(BASELINE_DATA_PATH)
    
    # 2. Initialize Model
    similarity_model = SimilarityModel()
    similarity_model.fit_baselines(baseline_dict)

    print("3. Fetching candidates from Google Places...")
    candidates_df = fetch_places_candidates(api_key, query, max_results=max_results)
    
    if candidates_df.empty:
        return pd.DataFrame()

    if 'website' in candidates_df.columns:
        candidates_df['website'] = candidates_df['website'].fillna("")

    profiles = []
    
    print(f"4. Profiling and scoring {len(candidates_df)} candidates...")
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
            
            # Combine the exact same types of text we used for the baselines
            candidate_text = " ".join([
                str(profile_data.get('Products_Product_Families', '')),
                str(profile_data.get('Capabilities_Manufacturing', '')),
                str(profile_data.get('Capabilities_Engineering_Design', '')),
                str(profile_data.get('Industries_Served', ''))
            ])
        else:
            profile_data = profile_input.to_dict()
            profile_data["Website_Check"] = "No website available to crawl"
            candidate_text = ""
            
        # Score the candidate against the EXIM baseline vectors
        score, best_match = similarity_model.score_candidate(candidate_text)
        
        profile_data['Similarity_Score'] = score
        profile_data['Best_Match'] = best_match
        profile_data['Score'] = f"{score * 100:.2f}%"
        
        profiles.append(profile_data)
        
    final_df = pd.DataFrame(profiles)
    
    if 'Similarity_Score' in final_df.columns:
        final_df = final_df.sort_values(by='Similarity_Score', ascending=False)
        
    display_columns = [
        'Company_Name_Normalized', 'Score', 'Best_Match', 'Company_Website_Final', 
        'Products_Product_Families', 'Capabilities_Manufacturing', 
        'Certifications_Website_Claims', 'Industries_Served'
    ]
    
    display_columns = [col for col in display_columns if col in final_df.columns]
    
    return final_df[display_columns]
