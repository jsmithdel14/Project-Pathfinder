# To run this later: pip install streamlit && streamlit run ui.py
import streamlit as st
import pandas as pd
from main import run_pipeline 

st.title("Team Exporter: Pathfinder Dashboard")

st.sidebar.header("Configuration")
# API key remains exclusively a user input, hidden like a password
api_key = st.sidebar.text_input("Google API Key", type="password")
query = st.sidebar.text_input("Search Query", "medical device manufacturing in Indiana")
# Slider capped at 20 to respect the Google Places single-call limit
max_results = st.sidebar.slider("Max Candidates", 1, 20, 20) 

if st.button("Generate & Evaluate Candidates"):
    if not api_key:
        st.error("Please provide a Google Places API Key.")
    else:
        with st.spinner("Running pipeline... this will take a moment to scrape websites."):
            df = run_pipeline(api_key, query, max_results)
            
            if df.empty:
                st.warning("No candidates found. Check your search query or API key.")
            else:
                st.success("Pipeline complete!")
                st.dataframe(df, use_container_width=True, hide_index=True)