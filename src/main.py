import os
import pandas as pd
from candidate_generation import fetch_places_candidates
from webscraper import scrape_many
from model import SimilarityModel

GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "YOUR_KEY_HERE")
PDL_DATA_PATH = "path/to.csv"

PRE_SCRAPED_BASELINES = {} # Ex: "Cook Medical": "Cook Medical is a privately owned medical device manufacturing company...

def main():
    print("1. Loading pre-scraped baseline data...")
    similarity_model = SimilarityModel()
    # Pass the entire dictionary so the model knows the names
    similarity_model.fit_baselines(PRE_SCRAPED_BASELINES)

    print("2. Fetching candidates from Google Places...")
    query = "medical device manufacturing in Indiana"
    candidates_df = fetch_places_candidates(GOOGLE_API_KEY, query, max_results=30)

    if candidates_df.empty:
        print("No candidates found.")
        return

    print(f"3. Scraping {len(candidates_df)} candidates...")
    candidate_urls = candidates_df['website'].dropna().tolist()
    scrape_results = scrape_many(candidate_urls)

    text_mapping = {res['url']: res['text'] for res in scrape_results}
    candidates_df['scraped_text'] = candidates_df['website'].map(text_mapping).fillna("")

    print("4. Scoring candidates against baseline...")
    # Apply now returns a tuple: (score, best_match_name)
    scores_and_matches = candidates_df['scraped_text'].apply(
        lambda txt: similarity_model.score_candidate(txt) if txt else (0.0, "None")
    )

    # Split the tuples into two separate columns
    candidates_df['similarity_score'] = [x[0] for x in scores_and_matches]
    candidates_df['best_match'] = [x[1] for x in scores_and_matches]

    top_candidates = candidates_df.sort_values(by='similarity_score', ascending=False)

    print("\n--- TOP EXPORT-READY CANDIDATES ---")
    for _, row in top_candidates.iterrows():
        name = row.get('name', 'Unknown')
        score = row.get('similarity_score', 0.0)
        best_match = row.get('best_match', 'None')
        print(f"{name} | Score: {score * 100:.2f}% (Matches: {best_match}) | URL: {row.get('website')}")

if __name__ == "__main__":
    main()