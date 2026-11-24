# Project-Pathfinder

### Deployed Run Instructions
Dashboard Link: [INSERT DEPLOYED URL HERE] Note - Final build not deployed yet

(No installation required—runs directly in your web browser.)

**How to Run a Search**

1. Open the Dashboard: Click the link above. (Note: If the app has been idle for a while, it may take 15–30 seconds to wake up.)

2. Enter Your Configuration (Left Sidebar):

    - Google API Key: Paste your Google Places API key, you can setup a new key here: https://developers.google.com/maps/documentation/places/web-service/get-api-key. Here is also a helpful tutorial video online if you need extra guidance generating a key: https://www.youtube.com/watch?v=uISyqtl3n1c

    - Search Query: Type the industry and location you want to target (e.g., medical device manufacturing in Indiana).

    - Max Candidates: Use the slider to choose how many companies to evaluate (up to 60).

**Run the Evaluation**

3. Click Generate & Evaluate Candidates.

    - Wait here, the tool is actively visiting and analyzing candidate websites, which can take a couple minutes depending on how many companies you selected. This gets up to date companies from google places so results may vary on the exact same queries as new places are added or removed in their api. 

**Reviewing Your Results**

Summary Table: Displays each candidate ranked by their overall match score, along with their closest verified EXIM exporter match, website, products, capabilities, certifications, and industries served.

Top Candidates (Model Insights): Click any of the Deep Dive expanders below the table to see a visual breakdown of how the top 5 candidates scored across Products, Capabilities, Certifications, and Industries Served.

**Download Full Report**

Click Download Detailed Excel Report at the bottom of the page to save a spreadsheet containing the top 3 closest exporter matches per candidate along with all underlying similarity, role-compatibility, and evidence-coverage metrics.

### Local Run Instructions
1. Ensure dependencies/libraries are installed in your python environment, they can be found in requirements.txt
    - For example run: "pip install -r requirements.txt" to install dependencies
2. Launch the Streamlit app
    - Run: "streamlit run app.py" in your python environment at the src folder, this will open the streamlit dashboard
3. Use the dashboard
    - You have to ensure you have a valid google place API key which can be found here: https://developers.google.com/maps/documentation/places/web-service/get-api-key
    - After inserting that you can adjust the query. Note by default this looks at farming equipment manufactors in Indiana, specifying the place and type of company is important to get strong candidates. Not all types of companies have strong baseline companies the model can use so results vary across industries.
    - You can also specify the amount of candidates to search for, by default google places API only does 20 but it is recommended to use the slider to get a larger candidate list of up to 60. Any more than 60 is not supported as it goes against the apis usage agreement for a single query. 
    - After inserting your api key and query hit the Generate button and this will start the search and profiling process.
4. Check the results
    - Once it finishes the results screen will show up and you can look at the intital top results.
    - Additional information is given for the top companies through visuals.
    - For a full breakdown of all the results click on the download button and this will download all the results into an excel sheet you can use to review all the results and missing areas of our profiling. 