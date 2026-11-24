# To run this: pip install streamlit && streamlit run ui.py
import streamlit as st
import pandas as pd
import io
from main import run_pipeline 

st.set_page_config(page_title="Pathfinder Dashboard", layout="wide")
st.title("Team Exporter: Pathfinder Dashboard")

st.sidebar.header("Configuration")
api_key = st.sidebar.text_input("Google API Key", type="password")
query = st.sidebar.text_input("Search Query", "medical device manufacturing in Indiana")
max_results = st.sidebar.slider("Max Candidates", 1, 60, 20)

if 'display_df' not in st.session_state:
    st.session_state['display_df'] = pd.DataFrame()
if 'full_df' not in st.session_state:
    st.session_state['full_df'] = pd.DataFrame()

if st.button("Generate & Evaluate Candidates"):
    if not api_key:
        st.error("Please provide a Google Places API Key.")
    else:
        with st.spinner("Running pipeline... this will take a moment to scrape websites."):
            display_df, full_df = run_pipeline(api_key, query, max_results)
            
            if display_df.empty:
                st.warning("No candidates found. Check your search query or API key.")
            else:
                st.session_state['display_df'] = display_df
                st.session_state['full_df'] = full_df

if not st.session_state['display_df'].empty:
    st.success("Pipeline complete!")
    
    # Retrieve the saved DataFrames
    display_df = st.session_state['display_df']
    full_df = st.session_state['full_df']
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.divider()
    st.subheader("Top Candidates: Model Insights")
    
    top_candidates = display_df.head(5)
    
    for _, row in top_candidates.iterrows():
        company = row.get('Company_Name_Normalized', 'Unknown')
        score = row.get('Composite_Readiness', '0.00%')
        match = row.get('Best_Match', 'None')
        
        detailed_row = full_df[(full_df['Candidate'] == company) & (full_df['Rank'] == 1)].iloc[0]
        
        with st.expander(f"Deep Dive: {company} - {score} Match"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Role Compatibility", f"{detailed_row.get('Role_Compatibility_Factor', 0):.2f}")
            col2.metric("Evidence Coverage", f"{detailed_row.get('Evidence_Coverage', 0):.0%}")
            col3.metric("Candidate Role", str(detailed_row.get('Candidate_Role', 'N/A')).replace('_', ' ').title())
            col4.metric("Baseline Match", str(match))
            
            st.markdown("**Group Similarity Breakdown**")
            
            chart_data = pd.DataFrame({
                "Category": ["Products", "Capabilities", "Certifications", "Industries Served"],
                "Similarity": [
                    float(detailed_row.get("Products_Similarity", 0) or 0),
                    float(detailed_row.get("Capabilities_Similarity", 0) or 0),
                    float(detailed_row.get("Certifications_Similarity", 0) or 0),
                    float(detailed_row.get("Industries_Served_Similarity", 0) or 0)
                ]
            }).set_index("Category")
            
            st.bar_chart(chart_data, y="Similarity")
    
    st.divider()
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        full_df.to_excel(writer, index=False, sheet_name='Detailed Results')

    st.download_button(
        label="Download Detailed Excel Report",
        data=buffer.getvalue(),
        file_name="pathfinder_detailed_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="Includes full capability metrics for the top 3 matches."
    )