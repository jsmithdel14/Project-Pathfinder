import requests
import pandas as pd

def fetch_places_candidates(api_key: str, query: str, max_results: int = 5) -> pd.DataFrame:
    """Hits Google Places API and returns a DataFrame of candidates."""
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri"
    }
    payload = {
        "textQuery": query,
        "maxResultCount": max_results
    }

    response = requests.post(endpoint, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        return pd.DataFrame()

    places = response.json().get("places", [])
    df = pd.json_normalize(places)

    if df.empty:
        return df

    df = df.rename(columns={
        "displayName.text": "name",
        "formattedAddress": "address",
        "websiteUri": "website"
    })

    if "displayName.languageCode" in df.columns:
        df = df.drop(columns=["displayName.languageCode"])

    return df

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