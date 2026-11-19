from __future__ import annotations

import math
from typing import Mapping

import pandas as pd
import torch
from sentence_transformers import SentenceTransformer, util

BASELINE_FIELD_GROUPS = {
    "Products": ["Products_Product_Families", "Products_Specific_Offerings"],
    "Capabilities": [
        "Capabilities_Manufacturing",
        "Capabilities_Engineering_Design",
        "Capabilities_Custom_OEM",
        "Capabilities_Services_Testing",
    ],
    "Certifications": ["Certifications_Current_Verified", "Certifications_Historical"],
    "Industries_Served": ["Industries_Served"],
}

CANDIDATE_FIELD_GROUPS = {
    "Products": ["Products_Product_Families", "Products_Specific_Offerings"],
    "Capabilities": [
        "Capabilities_Manufacturing",
        "Capabilities_Engineering_Design",
        "Capabilities_Custom_OEM",
        "Capabilities_Services_Testing",
    ],
    "Certifications": ["Certifications_Website_Claims", "Certification_Scope"],
    "Industries_Served": ["Industries_Served"],
}

DEFAULT_GROUP_WEIGHTS = {
    "Products": 0.35,
    "Capabilities": 0.35,
    "Certifications": 0.10,
    "Industries_Served": 0.20,
}

# Explicit starting assumptions for reliability adjustment.
BASELINE_CONFIDENCE_FACTORS = {
    "high": 1.00,
    "medium": 0.95,
    "low": 0.85,
}
DEFAULT_BASELINE_CONFIDENCE_FACTOR = 0.90

BUSINESS_ROLES = [
    "manufacturer",
    "manufacturer_and_distributor",
    "dealer_distributor",
    "systems_integrator_installer",
    "service_provider",
    "wholesaler_trader",
    "producer_processor",
    "technology_provider",
    "holding_company",
    "unknown",
]

ROLE_KEYWORDS = {
    "holding_company": ["holding company", "portfolio company", "investment platform"],
    "systems_integrator_installer": ["systems integrator", "system integration", "turn-key", "turnkey", "install and service", "design, sell, install", "installation"],
    "dealer_distributor": ["dealer", "dealership", "distributor", "equipment sales", "buying, selling", "sells and services", "sales, service, and parts", "rents", "leases"],
    "wholesaler_trader": ["wholesaler", "merchant wholesaler", "trading", "worldwide sourcing", "global sourcing", "importer", "export trading"],
    "producer_processor": ["producer", "processor", "processing facility", "food processing", "raises and processes", "sourcing, cleaning, packaging"],
    "technology_provider": ["software", "technology provider", "saas", "platform", "e-learning", "elearning"],
    "service_provider": ["service provider", "repair service", "field service", "consulting services", "testing laboratory"],
    "manufacturer": ["manufacturer", "manufactures", "manufacturing", "design and manufacture", "fabricates", "production facility", "made in the usa"],
}

ROLE_COMPATIBILITY = {
    "manufacturer": {
        "manufacturer": 1.00, "manufacturer_and_distributor": 0.98,
        "systems_integrator_installer": 0.88, "dealer_distributor": 0.78,
        "service_provider": 0.72, "wholesaler_trader": 0.70,
        "producer_processor": 0.68, "technology_provider": 0.72,
        "holding_company": 0.65, "unknown": 0.90,
    },
    "manufacturer_and_distributor": {
        "manufacturer": 0.98, "manufacturer_and_distributor": 1.00,
        "systems_integrator_installer": 0.90, "dealer_distributor": 0.90,
        "service_provider": 0.78, "wholesaler_trader": 0.82,
        "producer_processor": 0.70, "technology_provider": 0.75,
        "holding_company": 0.68, "unknown": 0.90,
    },
    "dealer_distributor": {
        "manufacturer": 0.78, "manufacturer_and_distributor": 0.90,
        "systems_integrator_installer": 0.88, "dealer_distributor": 1.00,
        "service_provider": 0.88, "wholesaler_trader": 0.88,
        "producer_processor": 0.65, "technology_provider": 0.70,
        "holding_company": 0.65, "unknown": 0.88,
    },
    "systems_integrator_installer": {
        "manufacturer": 0.88, "manufacturer_and_distributor": 0.90,
        "systems_integrator_installer": 1.00, "dealer_distributor": 0.88,
        "service_provider": 0.90, "wholesaler_trader": 0.72,
        "producer_processor": 0.68, "technology_provider": 0.82,
        "holding_company": 0.65, "unknown": 0.88,
    },
    "service_provider": {
        "manufacturer": 0.72, "manufacturer_and_distributor": 0.78,
        "systems_integrator_installer": 0.90, "dealer_distributor": 0.88,
        "service_provider": 1.00, "wholesaler_trader": 0.75,
        "producer_processor": 0.65, "technology_provider": 0.82,
        "holding_company": 0.65, "unknown": 0.85,
    },
    "wholesaler_trader": {
        "manufacturer": 0.70, "manufacturer_and_distributor": 0.82,
        "systems_integrator_installer": 0.72, "dealer_distributor": 0.88,
        "service_provider": 0.75, "wholesaler_trader": 1.00,
        "producer_processor": 0.80, "technology_provider": 0.68,
        "holding_company": 0.68, "unknown": 0.85,
    },
    "producer_processor": {
        "manufacturer": 0.68, "manufacturer_and_distributor": 0.70,
        "systems_integrator_installer": 0.68, "dealer_distributor": 0.65,
        "service_provider": 0.65, "wholesaler_trader": 0.80,
        "producer_processor": 1.00, "technology_provider": 0.65,
        "holding_company": 0.65, "unknown": 0.83,
    },
    "technology_provider": {
        "manufacturer": 0.72, "manufacturer_and_distributor": 0.75,
        "systems_integrator_installer": 0.82, "dealer_distributor": 0.70,
        "service_provider": 0.82, "wholesaler_trader": 0.68,
        "producer_processor": 0.65, "technology_provider": 1.00,
        "holding_company": 0.68, "unknown": 0.85,
    },
    "holding_company": {
        "manufacturer": 0.65, "manufacturer_and_distributor": 0.68,
        "systems_integrator_installer": 0.65, "dealer_distributor": 0.65,
        "service_provider": 0.65, "wholesaler_trader": 0.68,
        "producer_processor": 0.65, "technology_provider": 0.68,
        "holding_company": 1.00, "unknown": 0.80,
    },
    "unknown": {role: 0.90 for role in BUSINESS_ROLES},
}
ROLE_COMPATIBILITY["unknown"]["unknown"] = 1.00

MISSING_TEXT_VALUES = {
    "", "nan", "none", "n/a", "not applicable", "not publicly verified",
    "not publicly verified in reviewed sources",
    "not publicly verified in reviewed official sources",
    "not publicly verified on supplied website", "not assessed",
    "not assessed unless noted", "not assessed unless stated",
    "not assessed unless separately noted",
    "review cited page; not independently authenticated",
}


class SimilarityModel:
    def __init__(
        self,
        model_name: str = "BAAI/bge-base-en-v1.5",
        group_weights: Mapping[str, float] | None = None,
    ) -> None:
        self.model = SentenceTransformer(model_name)
        self.group_weights = dict(group_weights or DEFAULT_GROUP_WEIGHTS)
        self._validate_weights()
        self.baseline_names = []
        self.baseline_group_vectors = {}
        self.baseline_group_available = {}
        self.baseline_reliability = None
        self.baseline_confidence_labels = []
        self.baseline_roles = []

    def _validate_weights(self) -> None:
        if set(self.group_weights) != set(BASELINE_FIELD_GROUPS):
            raise ValueError("Group weights must match the four field groups.")
        if any(v < 0 for v in self.group_weights.values()):
            raise ValueError("Group weights cannot be negative.")
        if not math.isclose(sum(self.group_weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("Group weights must sum to 1.0.")

    @staticmethod
    def _clean_value(value) -> str:
        if pd.isna(value):
            return ""
        text = " ".join(str(value).split()).strip()
        lowered = text.lower()
        if lowered in MISSING_TEXT_VALUES or lowered.startswith("not publicly verified") or lowered.startswith("not assessed"):
            return ""
        return text

    @staticmethod
    def _required_columns(field_groups, baseline=False):
        columns = ["Company_Name_Normalized"]
        for fields in field_groups.values():
            columns.extend(fields)
        if baseline:
            columns.append("Confidence")
        return list(dict.fromkeys(columns))

    def _validate_columns(self, df, field_groups, label, baseline=False):
        missing = [c for c in self._required_columns(field_groups, baseline) if c not in df.columns]
        if missing:
            raise ValueError(f"{label} data is missing required columns: {missing}")

    def _group_to_text(self, row, group_name, field_groups) -> str:
        parts = []
        for field in field_groups[group_name]:
            text = self._clean_value(row.get(field, ""))
            if text:
                parts.append(f"{field}: {text}")
        return "\n".join(parts)

    @staticmethod
    def _confidence_factor(value) -> tuple[str, float]:
        if pd.isna(value):
            return "Unknown", DEFAULT_BASELINE_CONFIDENCE_FACTOR
        label = str(value).strip()
        lowered = label.lower()
        return label, BASELINE_CONFIDENCE_FACTORS.get(lowered, DEFAULT_BASELINE_CONFIDENCE_FACTOR)

    def _role_text(self, row: pd.Series, field_groups) -> str:
        parts = []
        for group in ("Products", "Capabilities", "Industries_Served"):
            for field in field_groups[group]:
                text = self._clean_value(row.get(field, ""))
                if text:
                    parts.append(text.lower())
        industry = self._clean_value(row.get("EXIM_Industry_Descriptions", ""))
        if industry:
            parts.append(industry.lower())
        return " ".join(parts)

    def infer_business_role(self, row: pd.Series, field_groups) -> str:
        text = self._role_text(row, field_groups)
        if not text:
            return "unknown"

        matched = {
            role: sum(text.count(keyword) for keyword in keywords)
            for role, keywords in ROLE_KEYWORDS.items()
        }
        manufacturer_score = matched.get("manufacturer", 0)
        dealer_score = matched.get("dealer_distributor", 0)
        if manufacturer_score > 0 and dealer_score > 0:
            return "manufacturer_and_distributor"

        priority = [
            "holding_company", "systems_integrator_installer",
            "dealer_distributor", "wholesaler_trader", "producer_processor",
            "technology_provider", "service_provider", "manufacturer",
        ]
        best_score = max(matched.values(), default=0)
        if best_score == 0:
            return "unknown"
        return next(role for role in priority if matched.get(role, 0) == best_score)

    @staticmethod
    def role_compatibility(candidate_role: str, baseline_role: str) -> float:
        return ROLE_COMPATIBILITY.get(candidate_role, ROLE_COMPATIBILITY["unknown"]).get(
            baseline_role, 0.85
        )

    def fit_baselines(self, baseline_df: pd.DataFrame) -> None:
        self._validate_columns(baseline_df, BASELINE_FIELD_GROUPS, "Baseline", baseline=True)
        df = baseline_df[baseline_df["Company_Name_Normalized"].notna()].copy()
        df["Company_Name_Normalized"] = df["Company_Name_Normalized"].astype(str).str.strip()
        df = df[df["Company_Name_Normalized"] != ""].reset_index(drop=True)
        if df.empty:
            raise ValueError("No usable baseline company rows were found.")

        self.baseline_names = df["Company_Name_Normalized"].tolist()
        confidence = [self._confidence_factor(v) for v in df["Confidence"]]
        self.baseline_confidence_labels = [x[0] for x in confidence]
        self.baseline_roles = [
            self.infer_business_role(row, BASELINE_FIELD_GROUPS)
            for _, row in df.iterrows()
        ]
        self.baseline_reliability = torch.tensor([x[1] for x in confidence], dtype=torch.float32)

        for group_name in BASELINE_FIELD_GROUPS:
            texts = [self._group_to_text(row, group_name, BASELINE_FIELD_GROUPS) for _, row in df.iterrows()]
            available = torch.tensor([bool(t) for t in texts], dtype=torch.bool)
            encoded_texts = [t if t else "[NO DATA]" for t in texts]
            vectors = self.model.encode(encoded_texts, convert_to_tensor=True, normalize_embeddings=True, show_progress_bar=False)
            self.baseline_group_vectors[group_name] = vectors
            self.baseline_group_available[group_name] = available.to(vectors.device)

        self.baseline_reliability = self.baseline_reliability.to(next(iter(self.baseline_group_vectors.values())).device)

    def score_candidate(self, candidate_row: pd.Series, top_k=3) -> list[dict]:
        if not self.baseline_group_vectors:
            raise RuntimeError("Call fit_baselines() before scoring candidates.")

        cand_vec, cand_available = {}, {}
        for group in CANDIDATE_FIELD_GROUPS:
            text = self._group_to_text(candidate_row, group, CANDIDATE_FIELD_GROUPS)
            cand_available[group] = bool(text)
            if text:
                cand_vec[group] = self.model.encode(text, convert_to_tensor=True, normalize_embeddings=True, show_progress_bar=False)

        n = len(self.baseline_names)
        device = next(iter(self.baseline_group_vectors.values())).device
        weighted_sum = torch.zeros(n, device=device)
        active_weights = torch.zeros(n, device=device)
        group_scores = {}

        for group, weight in self.group_weights.items():
            scores = torch.full((n,), float("nan"), device=device)
            if cand_available[group]:
                raw = util.cos_sim(cand_vec[group].to(device), self.baseline_group_vectors[group])[0]
                mask = self.baseline_group_available[group]
                scores[mask] = raw[mask]
                weighted_sum[mask] += raw[mask] * weight
                active_weights[mask] += weight
            group_scores[group] = scores

        overall = torch.full((n,), float("nan"), device=device)
        valid = active_weights > 0
        overall[valid] = weighted_sum[valid] / active_weights[valid]

        # Reliability adjustment is intentionally mild. Coverage is already based
        # on the original group weights before renormalization.
        coverage_factor = 0.75 + 0.25 * active_weights
        candidate_role = self.infer_business_role(candidate_row, CANDIDATE_FIELD_GROUPS)
        role_compatibility = torch.tensor(
            [self.role_compatibility(candidate_role, role) for role in self.baseline_roles],
            dtype=torch.float32, device=device
        )
        role_factor = 0.85 + (0.15 * role_compatibility)
        ranking_score = overall * coverage_factor * self.baseline_reliability * role_factor

        valid_idx = torch.nonzero(valid, as_tuple=False).flatten()
        if not len(valid_idx):
            return []
        k = min(max(int(top_k), 1), len(valid_idx))
        _, pos = torch.topk(ranking_score[valid_idx], k)
        top_idx = valid_idx[pos]

        out = []
        for idx_t in top_idx:
            i = int(idx_t.item())
            out.append({
                "match": self.baseline_names[i],
                "overall_similarity": float(overall[i].item()),
                "evidence_coverage": float(active_weights[i].item()),
                "coverage_factor": float(coverage_factor[i].item()),
                "baseline_confidence": self.baseline_confidence_labels[i],
                "baseline_reliability_factor": float(self.baseline_reliability[i].item()),
                "candidate_role": candidate_role,
                "baseline_role": self.baseline_roles[i],
                "role_compatibility_factor": float(role_compatibility[i].item()),
                "role_factor": float(role_factor[i].item()),
                "ranking_score": float(ranking_score[i].item()),
                "group_scores": {
                    g: None if torch.isnan(group_scores[g][i]) else float(group_scores[g][i].item())
                    for g in self.group_weights
                },
            })
        return out

    def score_candidates(self, candidate_df: pd.DataFrame, top_k=3) -> pd.DataFrame:
        self._validate_columns(candidate_df, CANDIDATE_FIELD_GROUPS, "Candidate")
        rows = []
        for _, row in candidate_df.iterrows():
            name = str(row["Company_Name_Normalized"]).strip()
            matches = self.score_candidate(row, top_k)
            if not matches:
                rows.append({"Candidate": name, "Rank": 1, "Baseline_Match": "Insufficient comparable evidence", "Overall_Similarity": None, "Evidence_Coverage": 0.0, "Coverage_Factor": None, "Baseline_Confidence": None, "Baseline_Reliability_Factor": None, "Candidate_Role": self.infer_business_role(row, CANDIDATE_FIELD_GROUPS), "Baseline_Role": None, "Role_Compatibility_Factor": None, "Role_Factor": None, "Ranking_Score": None, "Products_Similarity": None, "Capabilities_Similarity": None, "Certifications_Similarity": None, "Industries_Served_Similarity": None})
                continue
            for rank, m in enumerate(matches, 1):
                rows.append({
                    "Candidate": name, "Rank": rank, "Baseline_Match": m["match"],
                    "Overall_Similarity": m["overall_similarity"],
                    "Evidence_Coverage": m["evidence_coverage"],
                    "Coverage_Factor": m["coverage_factor"],
                    "Baseline_Confidence": m["baseline_confidence"],
                    "Baseline_Reliability_Factor": m["baseline_reliability_factor"],
                    "Candidate_Role": m["candidate_role"],
                    "Baseline_Role": m["baseline_role"],
                    "Role_Compatibility_Factor": m["role_compatibility_factor"],
                    "Role_Factor": m["role_factor"],
                    "Ranking_Score": m["ranking_score"],
                    "Products_Similarity": m["group_scores"]["Products"],
                    "Capabilities_Similarity": m["group_scores"]["Capabilities"],
                    "Certifications_Similarity": m["group_scores"]["Certifications"],
                    "Industries_Served_Similarity": m["group_scores"]["Industries_Served"],
                })
        return pd.DataFrame(rows)
