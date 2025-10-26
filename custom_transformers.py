"""
This module contains custom scikit-learn compatible transformers
for the job matching model pipeline.
"""
from scipy.sparse import csr_matrix

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

# Semantic imports may require these packages:
# pip install sentence-transformers torch
try:
    from sentence_transformers import SentenceTransformer, util
    import torch
    SEMANTIC_LIBRARIES_INSTALLED = True
except ImportError:
    SEMANTIC_LIBRARIES_INSTALLED = False


class TitleRatingTransformer(BaseEstimator, TransformerMixin):
    """
    Transforms the 'title_rating' column.
    Missing values (unrated titles) are imputed with 2.0 (neutral).
    """
    def __init__(self, neutral_value=2.0):
        self.neutral_value = neutral_value
        
    def fit(self, X, y=None):
        return self # Nothing to fit
        
    def transform(self, X, y=None):
        # X is expected to be a DataFrame
        # .fillna() handles None, np.nan, etc.
        # .values returns numpy array, .reshape(-1, 1) makes it a single column
        dense_output = X['title_rating'].fillna(self.neutral_value).values.reshape(-1, 1)
        return csr_matrix(dense_output)
    
    def get_feature_names_out(self, input_features=None):
        return ['title_rating']


class SkillFeaturesTransformer(BaseEstimator, TransformerMixin):
    """
    Transforms the 'skills' column (a list of skill objects) into three features:
    1. mean_skill_rating (unrated = 2.0)
    2. num_expert_skills (rated 3)
    3. num_novice_skills (rated 1)
    """
    def __init__(self, neutral_value=2.0, expert_val=3, novice_val=1):
        self.neutral_value = neutral_value
        self.expert_val = expert_val
        self.novice_val = novice_val

    def fit(self, X, y=None):
        return self # Nothing to fit

    def transform(self, X, y=None):
        # X is expected to be a DataFrame
        features = []
        
        # X['skills'] is a pandas Series, iterate over its values
        for skills_list in X['skills']:
            if not isinstance(skills_list, list) or not skills_list:
                # Handle missing or empty skills list
                features.append([self.neutral_value, 0, 0])
                continue

            ratings = []
            num_expert = 0
            num_novice = 0
            
            for skill in skills_list:
                # 'skill' is {'skill': 'Python', 'rating': 3}
                rating = skill.get('rating') # This is the proficiency rating
                
                if rating:
                    try:
                        rating_val = int(rating)
                        ratings.append(rating_val)
                        if rating_val == self.expert_val:
                            num_expert += 1
                        elif rating_val == self.novice_val:
                            num_novice += 1
                    except (ValueError, TypeError):
                        ratings.append(self.neutral_value)
                else:
                    # Skill is in the list but not rated by user
                    ratings.append(self.neutral_value)

            mean_rating = np.mean(ratings) if ratings else self.neutral_value
            features.append([mean_rating, num_expert, num_novice])
            
        dense_output = np.array(features)
        return csr_matrix(dense_output)

    def get_feature_names_out(self, input_features=None):
        return ['mean_skill_rating', 'num_expert_skills', 'num_novice_skills']


class SemanticHighlightScorer(BaseEstimator, TransformerMixin):
    """
    Transforms the 'job_description' column based on highlights.
    Solution B (Semantic Matching).
    """
    def __init__(self, highlights_df, model_name='all-MiniLM-L6-v2'):
        if not SEMANTIC_LIBRARIES_INSTALLED:
            raise ImportError("SemanticHighlightScorer requires 'sentence-transformers' and 'torch'. Please install them.")
        print(f"Initializing SemanticHighlightScorer...")
        self.highlights_df = highlights_df
        self.model_name = model_name
        self.model = None
        self.liked_phrases = []
        self.disliked_phrases = []
        self.liked_embeddings = None
        self.disliked_embeddings = None
        self.device = None

    def fit(self, X, y=None): # X here is the job_description column, but we don't use it for fitting this transformer
        print(f"Fitting SemanticHighlightScorer...")

        if self.highlights_df.empty:
            print("Warning: No highlights found in highlights_df. Semantic scores will all be 0.")
            self.liked_phrases = []
            self.disliked_phrases = []
        else:
            self.liked_phrases = self.highlights_df[self.highlights_df['type'] == 'like']['text'].tolist()
            self.disliked_phrases = self.highlights_df[self.highlights_df['type'] == 'dislike']['text'].tolist()

        if not self.liked_phrases and not self.disliked_phrases:
             print("Warning: No liked or disliked phrases found after filtering highlights_df. Semantic scores will all be 0.")
        
        if self.liked_phrases or self.disliked_phrases:
            print(f"Loading sentence transformer model '{self.model_name}'... (This may take a moment)")
            self.model = SentenceTransformer(self.model_name)
            print("Model loaded.")
            
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self.model.to(self.device)
            print(f"Using device: {self.device}")

            print(f"Encoding {len(self.liked_phrases)} 'like' and {len(self.disliked_phrases)} 'dislike' phrases...")
            if self.liked_phrases:
                self.liked_embeddings = self.model.encode(self.liked_phrases, convert_to_tensor=True, device=self.device)
            
            if self.disliked_phrases:
                self.disliked_embeddings = self.model.encode(self.disliked_phrases, convert_to_tensor=True, device=self.device)
                
            print("Highlight phrases encoded and stored.")
        else:
            print("No phrases to encode. Semantic model will not be loaded.")

        return self

    def transform(self, X, y=None):
        print(f"Generating semantic embeddings for {len(X)} job descriptions...")
        if self.model is None:
            print("No semantic model loaded (no highlights found). Returning zero scores.")
            # The output shape must match get_feature_names_out() (4 columns)
            # and it must be a sparse matrix to be compatible with save_npz.
            return csr_matrix((len(X), 4))

        descriptions = X.fillna('').tolist()
        desc_embeddings = self.model.encode(descriptions, convert_to_tensor=True, device=self.device, show_progress_bar=True)
        
        if self.liked_embeddings is not None and self.liked_embeddings.nelement() > 0:
            liked_sims = util.cos_sim(desc_embeddings, self.liked_embeddings)
            max_liked_scores, _ = liked_sims.max(dim=1) # Find the single best match
            mean_liked_scores = liked_sims.mean(dim=1) # Find the average match score
        else:
            max_liked_scores = torch.zeros(len(X), device=self.device)
            mean_liked_scores = torch.zeros(len(X), device=self.device)
            
        if self.disliked_embeddings is not None and self.disliked_embeddings.nelement() > 0:
            disliked_sims = util.cos_sim(desc_embeddings, self.disliked_embeddings)
            max_disliked_scores, _ = disliked_sims.max(dim=1) # Find the single best match
            mean_disliked_scores = disliked_sims.mean(dim=1) # Find the average match score
        else:
            max_disliked_scores = torch.zeros(len(X), device=self.device)
            mean_disliked_scores = torch.zeros(len(X), device=self.device)
            
        # Combine scores into a 4-column array
        scores = np.array(list(zip(max_liked_scores.cpu().numpy(), mean_liked_scores.cpu().numpy(), max_disliked_scores.cpu().numpy(), mean_disliked_scores.cpu().numpy())))
        
        print("Semantic scores calculated.")
        return csr_matrix(scores)

    def get_feature_names_out(self, input_features=None):
        return ['semantic_max_liked', 'semantic_mean_liked', 'semantic_max_disliked', 'semantic_mean_disliked']