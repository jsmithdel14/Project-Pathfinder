BGE SIMILARITY MODEL - VERIFIED CHANGE LOG AND OUTPUT GUIDE
===========================================================

This documentation is based on the latest main.py, model.py, baseline workbook,
candidate workbook, and generated candidate_similarity_results.xlsx.

1. BGE EMBEDDING MODEL
----------------------
The similarity engine now uses SentenceTransformer with:

    BAAI/bge-base-en-v1.5

Embeddings are normalized before cosine-similarity comparisons.

2. FIELD-GROUP SCORING INSTEAD OF ONE LARGE PROFILE STRING
----------------------------------------------------------
Company information is divided into four comparable semantic groups:

Products
  Baseline and candidate fields:
  - Products_Product_Families
  - Products_Specific_Offerings

Capabilities
  - Capabilities_Manufacturing
  - Capabilities_Engineering_Design
  - Capabilities_Custom_OEM
  - Capabilities_Services_Testing

Certifications
  Baseline:
  - Certifications_Current_Verified
  - Certifications_Historical

  Candidate:
  - Certifications_Website_Claims
  - Certification_Scope

Industries Served
  - Industries_Served

This allows the system to calculate separate semantic similarities for products,
capabilities, certifications, and industries rather than treating the entire
company profile as a single block of text.

3. FIELD-GROUP WEIGHTS
----------------------
The default weights are:

  Products:          35%
  Capabilities:      35%
  Certifications:    10%
  Industries Served: 20%

The weights must be nonnegative and sum to 1.0. model.py validates this during
model initialization.

4. MISSING/UNVERIFIED INFORMATION HANDLING
------------------------------------------
Known placeholder values such as "not publicly verified", "not assessed",
"n/a", and related variants are cleaned out before embeddings are generated.
They therefore do not become meaningful company-profile evidence.

If a field group contains no usable information, that group is marked
unavailable instead of forcing artificial semantic evidence into the score.

5. BASELINE PRE-ENCODING
------------------------
fit_baselines() validates the baseline data, stores baseline company names,
infer roles, converts confidence labels into reliability factors, and encodes
each available baseline field group.

The baseline vectors are stored so candidate companies can subsequently be
compared against them.

6. BASELINE CONFIDENCE / RELIABILITY
------------------------------------
The baseline workbook's Confidence column now affects ranking.

Factors in the current code:

  High:    1.00
  Medium:  0.95
  Low:     0.85
  Unknown/unrecognized value: 0.90

This is deliberately a relatively mild adjustment. A strong semantic match is
not discarded merely because its baseline record has somewhat lower confidence,
but a better-supported baseline receives more trust in the final ranking.

7. EVIDENCE COVERAGE
--------------------
The program tracks how much of the intended weighted information is actually
comparable between a candidate and each baseline company.

Evidence_Coverage is the sum of the original weights of field groups that have
usable information on both sides.

For example, when Products (0.35), Capabilities (0.35), and Industries (0.20)
are comparable but Certifications (0.10) are not, Evidence_Coverage is 0.90.

8. COVERAGE FACTOR
------------------
Evidence coverage is converted into a deliberately mild final-score adjustment:

    Coverage_Factor = 0.75 + (0.25 * Evidence_Coverage)

A match with complete evidence therefore receives 1.00. Less-complete evidence
reduces the final ranking without automatically eliminating the match.

9. OVERALL SIMILARITY WITH RENORMALIZATION
------------------------------------------
Overall_Similarity is the weighted semantic similarity of the field groups that
can actually be compared.

The active weights are renormalized. Thus a missing field group is not treated
as a similarity of zero. Missing evidence is accounted for separately through
Evidence_Coverage and Coverage_Factor.

10. BUSINESS-ROLE INFERENCE
---------------------------
The model now infers a business role from product, capability, and industry text.
For baseline profiles it can also use EXIM_Industry_Descriptions when available.

Possible roles are:

  manufacturer
  manufacturer_and_distributor
  dealer_distributor
  systems_integrator_installer
  service_provider
  wholesaler_trader
  producer_processor
  technology_provider
  holding_company
  unknown

Role inference is keyword-based. If both manufacturer and dealer/distributor
evidence is detected, the role is manufacturer_and_distributor.

11. ROLE COMPATIBILITY
----------------------
Candidate and baseline roles are compared with an explicit compatibility matrix.
Exact or closely related roles generally receive stronger compatibility than
materially different business roles.

The value from this table is Role_Compatibility_Factor.

12. MILD ROLE ADJUSTMENT
------------------------
Role compatibility is converted into another deliberately mild multiplier:

    Role_Factor = 0.85 + (0.15 * Role_Compatibility_Factor)

This prevents role classification from completely dominating semantic similarity.

13. FINAL RANKING SCORE
-----------------------
The score actually used to rank baseline matches is:

    Ranking_Score = Overall_Similarity
                    * Coverage_Factor
                    * Baseline_Reliability_Factor
                    * Role_Factor

Thus Ranking_Score, rather than raw Overall_Similarity alone, determines the top
matches.

14. TOP-3 RESULTS
-----------------
main.py currently has TOP_K = 3.

For each candidate with usable comparable evidence, the program returns the
three baseline companies with the highest Ranking_Score (or fewer if fewer
valid baseline comparisons exist).

15. INSUFFICIENT COMPARABLE EVIDENCE
------------------------------------
If no field group can be compared for a candidate, the output records:

    Baseline_Match = Insufficient comparable evidence
    Evidence_Coverage = 0

and leaves unavailable calculated scores blank.

16. LOCAL INPUT VALIDATION
--------------------------
main.py expects both input files in the same directory as the Python files:

    Indiana_EXIM_Exporter_Profiles_working_v20.xlsx
    company_profiles_website_first.xlsx

It reads the "Company Profiles" sheet using openpyxl.

Required fields are built directly from the field-group definitions. Baseline
data additionally requires Confidence.

Missing required columns cause a ValueError. Rows with empty normalized company
names are filtered out.

17. TERMINAL OUTPUT
-------------------
When run locally, main.py prints:

  - baseline and candidate loading status/counts
  - BGE model loading message
  - baseline encoding/role inference status
  - candidate scoring status
  - each candidate's ranked matches
  - ranking score
  - raw overall similarity
  - evidence coverage
  - coverage factor
  - baseline confidence/reliability
  - candidate and baseline roles
  - role compatibility
  - products similarity
  - capabilities similarity
  - certifications similarity
  - industries-served similarity

18. EXCEL EXPORT
----------------
The complete results DataFrame is saved as:

    candidate_similarity_results.xlsx

in the same directory as main.py.

The pandas index is not written to Excel.


EXACT OUTPUT EXCEL COLUMN GUIDE
===============================

1. Candidate
------------
The normalized name of the candidate company being evaluated.

2. Rank
-------
The candidate's match position after sorting by Ranking_Score. With TOP_K = 3,
normal scored candidates receive ranks 1, 2, and 3.

3. Baseline_Match
-----------------
The existing Indiana EXIM exporter matched against the candidate. If no usable
comparison is possible, this contains "Insufficient comparable evidence".

4. Overall_Similarity
---------------------
The raw weighted semantic similarity across the field groups that are available
for both companies. Available group weights are renormalized, so this score
measures similarity using the evidence that can actually be compared.

It is NOT the final ranking score.

5. Evidence_Coverage
--------------------
The fraction of the original weighted profile for which candidate and baseline
both have comparable evidence. It is based on the four group weights.

A value of 0.90 means 90% of the intended weighted evidence was comparable.

6. Coverage_Factor
------------------
The multiplier derived from Evidence_Coverage:

    0.75 + 0.25 * Evidence_Coverage

It applies a mild penalty to matches supported by incomplete evidence.

7. Baseline_Confidence
----------------------
The original Confidence label from the baseline exporter workbook for the
matched baseline company, such as High, Medium, or Low.

8. Baseline_Reliability_Factor
------------------------------
The numerical multiplier assigned to Baseline_Confidence:

    High   = 1.00
    Medium = 0.95
    Low    = 0.85

Unknown or other unmatched labels use 0.90.

9. Candidate_Role
-----------------
The business role inferred for the candidate from its profile text.

Examples include manufacturer, dealer_distributor,
manufacturer_and_distributor, systems_integrator_installer, and unknown.

10. Baseline_Role
-----------------
The inferred business role of the matched baseline exporter.

11. Role_Compatibility_Factor
-----------------------------
The compatibility value looked up from the role-compatibility matrix using the
candidate role and baseline role.

A value of 1.00 represents full compatibility under the configured matrix.
Lower values indicate progressively less compatible business roles.

12. Role_Factor
---------------
The mild ranking multiplier calculated from role compatibility:

    Role_Factor = 0.85 + 0.15 * Role_Compatibility_Factor

13. Ranking_Score
-----------------
The final value used to determine Rank:

    Overall_Similarity
      * Coverage_Factor
      * Baseline_Reliability_Factor
      * Role_Factor

This is the primary number to use when interpreting the model's final ordering.

14. Products_Similarity
-----------------------
BGE cosine similarity for the Products field group. The group consists of
product families and specific offerings. Blank means comparable product evidence
was unavailable for that candidate/baseline pair.

15. Capabilities_Similarity
---------------------------
BGE cosine similarity for the Capabilities group, covering manufacturing,
engineering/design, custom/OEM, and services/testing fields. Blank means the
pair had no comparable capability evidence.

16. Certifications_Similarity
------------------------------
BGE cosine similarity for certification information.

Baseline certification evidence comes from Certifications_Current_Verified and
Certifications_Historical. Candidate evidence comes from
Certifications_Website_Claims and Certification_Scope.

Blank means comparable certification evidence was unavailable.

17. Industries_Served_Similarity
--------------------------------
BGE cosine similarity between the companies' Industries_Served evidence. Blank
means comparable industry evidence was unavailable.


HOW TO INTERPRET ONE RESULT
===========================

Read a row in roughly this order:

1. Candidate and Baseline_Match identify the comparison.
2. Rank tells where this baseline placed for the candidate.
3. Ranking_Score is the final ranking value.
4. Overall_Similarity shows the underlying semantic similarity before the
   coverage, baseline-reliability, and role adjustments.
5. Evidence_Coverage tells you how complete the actual comparison was.
6. Products/Capabilities/Certifications/Industries similarities show which
   dimensions are driving the semantic match.
7. Candidate_Role, Baseline_Role, and Role_Compatibility_Factor show whether
   the companies perform reasonably compatible business functions.
8. Baseline_Confidence and Baseline_Reliability_Factor show how much trust the
   model assigned to the underlying baseline profile.

IMPORTANT INTERPRETATION POINT
==============================

Rank 1 means "highest Ranking_Score among the baseline comparisons evaluated for
this candidate." It should not be read as an independently calibrated probability
that the company will become an exporter or obtain EXIM financing. The output is
a similarity/ranking system using the profile evidence and explicit adjustments
implemented in the current model.py.
