# -*- coding: utf-8 -*-
import os
import json
import pandas as pd
# Use a free, local embedding model via sentence-transformers
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from PyPDF2 import PdfReader

# Constants
MAX_CHARS = 16384
DESCRIPTION_SNIPPET_LENGTH = 1000 # Max characters to take from the description for embedding
BOILERPLATE_SKIP_CHARS = 200 # Skips this many characters from the start if description is long
DICE_DATA_FILE = "dice_job_data.json"
CHECKPOINT_INTERVAL = 100 # Save results every X jobs processed

# --- SCORING PARAMETERS ---
MODEL_NAME = 'all-mpnet-base-v2' # More powerful local embedding model

# New fields for the separated scores
SEMANTIC_SCORE_FIELD = 'semantic_score_v2'
SKILLS_SCORE_FIELD = 'skills_intersection_score'
# ------------------------------


def extract_text_from_pdf(pdf_path):
    """
    Extracts text content from all pages of a PDF file.
    """
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            # Ensure text extraction is not None before concatenating
            extracted = page.extract_text()
            if extracted:
                text += extracted
        return text.strip()
    except Exception as e:
        print(f"Error reading PDF file {pdf_path}: {e}")
        return ""

def save_jobs_to_json(data, filename=DICE_DATA_FILE):
    """Saves the job data list back to the specified JSON file for checkpointing."""
    print(f"\n--- Saving checkpoint to {filename} ---")
    try:
        # Use 'w' mode to overwrite the file and 'utf-8' encoding for compatibility
        with open(filename, 'w', encoding='utf-8') as f:
            # Using indent=4 makes the JSON file human-readable
            json.dump(data, f, indent=4)
        print("Checkpoint saved successfully.")
    except Exception as e:
        print(f"Error saving data to JSON: {e}")

def get_job_embedding_input(job):
    """
    Constructs the targeted text input for the semantic embedding model.
    It applies a simple heuristic to skip potential boilerplate at the start of the description.
    """
    job_title = job.get('title', '')
    job_skills = ", ".join(job.get('skills', []))
    job_description = job.get('description', '')
    
    start_index = 0
    # Apply the heuristic: skip the first BOILERPLATE_SKIP_CHARS if the description is long
    if len(job_description) > DESCRIPTION_SNIPPET_LENGTH + BOILERPLATE_SKIP_CHARS:
        start_index = BOILERPLATE_SKIP_CHARS

    # Take the relevant snippet
    job_description_snippet = job_description[start_index : start_index + DESCRIPTION_SNIPPET_LENGTH]

    # Combine high-signal text for embedding
    return f"Job Title: {job_title}. Key Skills: {job_skills}. Context: {job_description_snippet}"


def calculate_semantic_similarity(resume_vector, job_text_for_embedding, embedder, max_chars=MAX_CHARS):
    """
    Calculates the cosine similarity (semantic score) between the resume vector 
    and the targeted job text.
    """
    if not job_text_for_embedding or job_text_for_embedding == 'N/A':
        return 0.0

    # The input text is already targeted and should be within MAX_CHARS, but we truncate defensively
    if len(job_text_for_embedding) > max_chars:
        job_text_for_embedding = job_text_for_embedding[:max_chars]

    # Generate vector for the job description using the 'all-mpnet-base-v2' model
    job_description_vector = embedder.encode(job_text_for_embedding, convert_to_numpy=True)

    # Cosine similarity requires the input to be in a 2D array format
    score = cosine_similarity([resume_vector], [job_description_vector])[0][0]
    return float(score)

def calculate_skills_intersection_score(resume_text, job_skills):
    """
    Calculates a score based on how many of the job's required skills
    are explicitly mentioned in the resume text.
    Score = (Matched Skills) / (Total Unique Job Skills)
    """
    if not job_skills or not resume_text:
        return 0.0

    # Convert resume text to lowercase for case-insensitive matching
    resume_text_lower = resume_text.lower()
    
    match_count = 0
    # Use a set for unique job skills to avoid double counting
    unique_job_skills = set(job_skills)
    
    for skill in unique_job_skills:
        skill_lower = skill.lower().strip()
        # Simple check: if the skill phrase is found in the resume text
        if skill_lower and skill_lower in resume_text_lower:
            match_count += 1
            
    # Score is the ratio of matched skills to total required unique skills
    score = match_count / len(unique_job_skills)
    
    # Score is a ratio, so it's already between 0.0 and 1.0
    return score

def score_jobs_against_resume(resume_file="DougOsborne_Resume.pdf", job_data_file=DICE_DATA_FILE, checkpoint_interval=CHECKPOINT_INTERVAL):
    """
    Main function to initialize the embedding model, load the resume,
    calculate separate similarity scores for jobs in the data file, and save results.
    """
    # --- Local Embedding Setup ---
    try:
        print(f"Initializing local embedding model ({MODEL_NAME})...")
        embedder = SentenceTransformer(MODEL_NAME)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"FATAL ERROR: Could not load SentenceTransformer model: {e}")
        print("Ensure you have installed the required library: pip install sentence-transformers")
        return # Stop execution if model fails to load

    # 1. Prepare Resume Data and Vector (Calculated only once)
    if not os.path.exists(resume_file):
        print(f"FATAL ERROR: Resume file '{resume_file}' not found.")
        return

    resume_text = extract_text_from_pdf(resume_file)
    if not resume_text:
        print("FATAL ERROR: Could not extract text from resume.")
        return

    if len(resume_text) > MAX_CHARS:
        resume_text = resume_text[:MAX_CHARS]
        print(f"Warning: Resume text truncated to {MAX_CHARS} characters.")

    print("\n--- Generating Resume Vector (One time) ---")
    resume_vector = embedder.encode(resume_text, convert_to_numpy=True)
    print("Resume vector generated. Ready to score jobs.")


    # 2. Load Jobs Data
    print(f"\n--- Loading job data from {job_data_file} ---")
    if not os.path.exists(job_data_file):
        print(f"WARNING: Job data file '{job_data_file}' not found. Creating empty list.")
        jobs_data = []
    else:
        try:
            with open(job_data_file, 'r', encoding='utf-8') as f:
                jobs_data = json.load(f)
            print(f"Loaded {len(jobs_data)} jobs.")
        except json.JSONDecodeError as e:
            print(f"FATAL ERROR: Failed to decode JSON from {job_data_file}: {e}")
            return
        except Exception as e:
            print(f"FATAL ERROR: An unexpected error occurred while loading job data: {e}")
            return
            
    if not jobs_data:
        print("No job data found to process. Exiting.")
        return

    # 3. Process Jobs
    print("\n--- Starting Job Matching and Scoring ---")
    jobs_processed_since_checkpoint = 0
    jobs_calculated_in_this_run = 0 # Tracks total jobs scored in the current session
    total_semantic_score = 0.0 # Running sum for semantic score average
    total_skills_score = 0.0 # Running sum for skills score average


    for i, job in enumerate(jobs_data):
        job_index = i + 1
        
        # Get existing scores (for display/recalculation check)
        old_score = job.get('resume_score', 0.0)
        semantic_score = job.get(SEMANTIC_SCORE_FIELD, 0.0)
        skills_score = job.get(SKILLS_SCORE_FIELD, 0.0)

        # Check if scoring is needed (i.e., if either new score is missing or 0.0)
        semantic_score_exists = semantic_score > 0.0
        skills_score_exists = skills_score > 0.0
        needs_scoring = not (semantic_score_exists and skills_score_exists)
        
        job_title = job.get('title', 'Untitled')


        if needs_scoring:
            # --- CALCULATE SCORES ---
            job_skills = job.get('skills', [])
            job_embedding_input = get_job_embedding_input(job)

            try:
                # 3a. Calculate Semantic Score
                if job_embedding_input.strip():
                    semantic_score = calculate_semantic_similarity(resume_vector, job_embedding_input, embedder)
                else:
                    semantic_score = 0.0
                
                # 3b. Calculate Skills Intersection Score
                skills_score = calculate_skills_intersection_score(resume_text, job_skills)

                # Add the new fields (update the dictionary)
                job[SEMANTIC_SCORE_FIELD] = round(semantic_score, 4)
                job[SKILLS_SCORE_FIELD] = round(skills_score, 4)
                
                # Update running totals *only* if a new score was calculated
                total_semantic_score += semantic_score
                total_skills_score += skills_score
                jobs_calculated_in_this_run += 1
                jobs_processed_since_checkpoint += 1
                
            except Exception as e:
                # Log error but continue
                print(f"Job {job_index} ({job_title}): Error during scoring: {e}. Skipping update for this job.")

        
        # --- NEW: Logging Output ---
        current_avg_semantic = total_semantic_score / jobs_calculated_in_this_run if jobs_calculated_in_this_run > 0 else 0.0
        current_avg_skills = total_skills_score / jobs_calculated_in_this_run if jobs_calculated_in_this_run > 0 else 0.0
        
        print(
            f"Job {job_index:<4}/{len(jobs_data)} "
            f"| Title: {job_title:<50.50} "
            f"| Old Score: {old_score:.4f} "
            f"| Semantic: {job.get(SEMANTIC_SCORE_FIELD):.4f} "
            f"| Skills: {job.get(SKILLS_SCORE_FIELD):.4f} "
            f"| Avg Sem: {current_avg_semantic:.4f} "
            f"| Avg Skill: {current_avg_skills:.4f} "
            f"| Status: {'SCORED' if needs_scoring else 'SKIPPED'}"
        )
        # --- End Logging Output ---

        # 4. Save Checkpoint every CHECKPOINT_INTERVAL
        # Only save if we actually processed jobs since the last save
        if jobs_processed_since_checkpoint >= checkpoint_interval and needs_scoring:
            save_jobs_to_json(jobs_data, job_data_file)
            jobs_processed_since_checkpoint = 0
            
    # 5. Final Save
    if jobs_processed_since_checkpoint > 0:
        print("\n--- Processing finished. Performing final save. ---")
        save_jobs_to_json(jobs_data, job_data_file)
    else:
        print("\n--- Processing finished. No unsaved changes since last checkpoint. ---")
        
    print(f"\n--- Summary ---")
    print(f"Total jobs loaded: {len(jobs_data)}")
    print(f"New scores calculated: {jobs_calculated_in_this_run}")

if __name__ == '__main__':
    score_jobs_against_resume()
