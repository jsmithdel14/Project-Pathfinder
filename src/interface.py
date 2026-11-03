# To run this later: pip install streamlit && streamlit run ui.py
import streamlit as st
import pandas as pd
# from main import run_pipeline

st.title("Team Exporter: Pathfinder Dashboard")

st.sidebar.header("Configuration")
api_key = st.sidebar.text_input("Google API Key", type="password")
query = st.sidebar.text_input("Search Query", "medical device manufacturing in Indiana")
max_results = st.sidebar.slider("Max Candidates", 1, 50, 5)

if st.button("Generate & Evaluate Candidates"):
    if not api_key:
        st.error("Please provide an API Key.")
    else:
        with st.spinner("Running pipeline..."):
            # Execute pipeline and return top_candidates_df
            # df = run_pipeline(api_key, query, max_results)

            # Mock placeholder
            df = pd.DataFrame({
                "Company": ["Micropulse", "Cook Medical"],
                "Score": [88.5, 92.1]
            })

            st.success("Pipeline complete.")
            st.dataframe(df)