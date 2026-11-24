import time
import requests
import pandas as pd

def fetch_places_candidates(api_key, query, max_results):
    """Fetches candidate companies from the Google Places API based on a search query."""
    url = "https://places.googleapis.com/v1/places:searchText"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        # Important: Request only the exact fields we need to keep api costs down
        "X-Goog-FieldMask": "places.displayName.text,places.formattedAddress,places.websiteUri,nextPageToken"
    }
    
    results = []
    page_token = ""
    
    while len(results) < max_results:
        payload = {
            "textQuery": query,
            "includedType": "manufacturer",
            "strictTypeFiltering": True,
            "pageSize": 20
        }
        
        if page_token:
            payload["pageToken"] = page_token
            time.sleep(2)
            
        response = requests.post(url, headers=headers, json=payload).json()
        
        if "places" in response:
            results.extend(response["places"])
            
        page_token = response.get("nextPageToken")
        
        if not page_token:
            break

    results = results[:max_results]
    
    if not results:
        return pd.DataFrame()
        
    df = pd.json_normalize(results)

    rename_map = {
        "displayName.text": "name",
        "formattedAddress": "address",
        "websiteUri": "website"
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    for col in ["name", "address", "website"]:
        if col not in df.columns:
            df[col] = ""
            
    return df.head(max_results)


def merge_with_company_data(places_df: pd.DataFrame, pdl_csv_path: str) -> pd.DataFrame:
    """Merges Google Places candidates with local PDL company data based on name."""
    if places_df.empty:
        return places_df

    pdl_df = pd.read_csv(pdl_csv_path)

    places_df['merge_name'] = places_df['name'].astype(str).str.lower().str.strip()
    pdl_df['merge_name'] = pdl_df['name'].astype(str).str.lower().str.strip()

    merged_df = pd.merge(places_df, pdl_df, on='merge_name', how='left')
    return merged_df.drop(columns=['merge_name'])
