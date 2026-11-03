import torch
from sentence_transformers import SentenceTransformer, util

class SimilarityModel:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
        self.baseline_vectors = None
        self.baseline_names = None

    def fit_baselines(self, baseline_dict: dict):
        """Encodes multiple baseline texts and stores their names."""
        self.baseline_names = list(baseline_dict.keys())
        valid_texts = list(baseline_dict.values())
        self.baseline_vectors = self.model.encode(valid_texts, convert_to_tensor=True)

    def score_candidate(self, candidate_text: str) -> tuple[float, str]:
        """Returns the highest similarity score and the name of the matched baseline."""
        if self.baseline_vectors is None:
            raise RuntimeError("Must call fit_baselines() before scoring candidates.")

        if not candidate_text.strip():
            return 0.0, "None"

        candidate_vector = self.model.encode(candidate_text, convert_to_tensor=True)
        cosine_scores = util.cos_sim(candidate_vector, self.baseline_vectors)

        # Find the index of the highest score to get the matching company name
        best_idx = torch.argmax(cosine_scores).item()
        max_score = cosine_scores[0][best_idx].item()
        matched_company = self.baseline_names[best_idx]

        return max_score, matched_company