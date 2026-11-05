import requests
import pandas as pd
import time

def fetch_places_candidates(api_key: str, query: str, max_results: int = 60) -> pd.DataFrame:
    """Hits Google Places API and handles pagination to return up to 60 candidates."""
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri"
    }
    
    all_places = []
    next_page_token = ""
    
    # Loop until we reach the max_results target or run out of pages
    while len(all_places) < max_results:
        # Request up to 20 results per page, or whatever is left to hit the target
        remaining_needed = max_results - len(all_places)
        page_size = min(remaining_needed, 20)
        
        payload = {
            "textQuery": query,
            "maxResultCount": page_size
        }
        
        if next_page_token:
            payload["pageToken"] = next_page_token
            # Google requires a short delay before a page token becomes active
            time.sleep(2) 
            
        response = requests.post(endpoint, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
            break

        data = response.json()
        places = data.get("places", [])
        all_places.extend(places)
        
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break # Exit the loop if there are no more pages of results
            
    if not all_places:
        return pd.DataFrame()
        
    df = pd.json_normalize(all_places)
    df = df.rename(columns={
        "displayName.text": "name",
        "formattedAddress": "address",
        "websiteUri": "website"
    })
    
    if "displayName.languageCode" in df.columns:
        df = df.drop(columns=["displayName.languageCode"])
        
    # Ensure we return exactly the requested number if we slightly overshot
    return df.head(max_results)

# def fetch_places_candidates(api_key: str, query: str, max_results: int = 5) -> pd.DataFrame:
#     """Hits Google Places API and returns a DataFrame of candidates."""
#     endpoint = "https://places.googleapis.com/v1/places:searchText"
#     headers = {
#         "Content-Type": "application/json",
#         "X-Goog-Api-Key": api_key,
#         "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri"
#     }
#     payload = {
#         "textQuery": query,
#         "maxResultCount": max_results
#     }

#     response = requests.post(endpoint, headers=headers, json=payload)
#     if response.status_code != 200:
#         print(f"Error {response.status_code}: {response.text}")
#         return pd.DataFrame()

#     places = response.json().get("places", [])
#     df = pd.json_normalize(places)

#     if df.empty:
#         return df

#     df = df.rename(columns={
#         "displayName.text": "name",
#         "formattedAddress": "address",
#         "websiteUri": "website"
#     })

#     if "displayName.languageCode" in df.columns:
#         df = df.drop(columns=["displayName.languageCode"])

#     return df

def merge_with_company_data(places_df: pd.DataFrame, pdl_csv_path: str) -> pd.DataFrame:
    """Merges Google Places candidates with local PDL company data based on name."""
    if places_df.empty:
        return places_df

    pdl_df = pd.read_csv(pdl_csv_path)

    # Normalize names for merging
    places_df['merge_name'] = places_df['name'].astype(str).str.lower().str.strip()
    pdl_df['merge_name'] = pdl_df['name'].astype(str).str.lower().str.strip()

    merged_df = pd.merge(places_df, pdl_df, on='merge_name', how='left')
    return merged_df.drop(columns=['merge_name'])