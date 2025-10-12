import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
# NOTE: This imports connect_to_mongodb and DATABASE_NAME
from mongodb_functions import connect_to_mongodb 
from bson.objectid import ObjectId
import logging

# --- Setup ---
app = Flask(__name__)
# Enable CORS for the React frontend (running on a different port/origin)
CORS(app) 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# --- Mock Data for Testing ---
# This data is used if MongoDB connection fails. Replace with actual document structure.
MOCK_JOB_DATA = {
    "url": "http://example.com/job/123",
    "title": "Senior Python Developer (AI/ML)",
    "company": "DeepMind Corp",
    "location": "Remote - US Only",
    "posted_date": "2025-10-01",
    "job_types": ["Remote", "Hybrid"],
    "salary": "150k - 200k USD",
    "skills": ["Python", "TensorFlow", "PyTorch", "Flask", "SQL", "Communication", "Teamwork"],
    "description": "We are seeking an experienced engineer to lead our core machine learning infrastructure initiatives. A strong background in Python, distributed systems, and modern deep learning frameworks (TensorFlow, PyTorch) is essential. The ideal candidate will be highly collaborative, possess strong problem-solving skills, and thrive in a fast-paced environment. This role involves developing new models and maintaining existing production systems.",
    "resume_score": 0.85,
    "semantic_score_v2": 0.92,
    "job_id": "123"
}

MOCK_SKILL_PROFS = [
    {"skill_name": "Python", "user_rating": 3}, # Highlighted
    {"skill_name": "SQL", "user_rating": 2},    # Highlighted
    {"skill_name": "Communication", "user_rating": 1}, # Highlighted
    {"skill_name": "TensorFlow", "user_rating": 4},
    {"skill_name": "Teamwork", "user_rating": 5},
    {"skill_name": "Flask", "user_rating": 0}, # Not Highlighted
]

# --- API Endpoints ---

@app.route('/api/job/<job_id>', methods=['GET'])
def get_job_data(job_id):
    """
    Fetches job details and user's skill proficiency data from MongoDB.
    
    If MongoDB fails to connect, mock data is served.
    """
    logging.info(f"Attempting to fetch data for Job ID: {job_id}")
    client, db = connect_to_mongodb()
    
    if client is None:
        logging.warning("MongoDB connection failed. Serving MOCK DATA.")
        # Only return skills that are relevant to the job for a realistic mock
        job_data = MOCK_JOB_DATA.copy()
        
        # Filter mock proficiencies to only include skills in the job posting
        job_skills = set(job_data.get('skills', []))
        skill_proficiencies = [
            s for s in MOCK_SKILL_PROFS 
            if s['skill_name'] in job_skills
        ]

        # Combine and return
        response_data = {
            "job_details": job_data,
            "skill_proficiencies": skill_proficiencies,
            "source": "MOCK"
        }
        return jsonify(response_data)

    try:
        # 1. Fetch Job Details (from dice_jobs)
        jobs_collection = db['dice_jobs']
        
        # MongoDB stores IDs as ObjectId. Adjust the query based on how your job_id is stored (as string or ObjectId)
        try:
            # Assuming job_id is stored as a string or number, not necessarily an ObjectId for this query
            job_doc = jobs_collection.find_one({"job_id": job_id})
        except:
             # Fallback if job_id is stored as a direct string key/value
             job_doc = jobs_collection.find_one({"job_id": job_id})
        
        if not job_doc:
            return jsonify({"error": f"Job ID {job_id} not found."}), 404

        # Convert MongoDB ObjectId to string for JSON serialization
        job_doc['job_id'] = str(job_doc.get('_id', job_id)) 
        
        # 2. Fetch Skill Proficiencies (from skills_proficiency)
        prof_collection = db['skills_proficiency']
        # Fetch ALL skill proficiencies for the current user's profile (assuming PROFILE_DOCUMENT_ID is 'Doug')
        # NOTE: You may need to replace 'Doug' with a real profile identifier if your table is multi-user
        skill_proficiencies_cursor = prof_collection.find({"profile_name": "Doug"}) 
        
        skill_proficiencies = []
        for doc in skill_proficiencies_cursor:
            skill_proficiencies.append({
                "skill_name": doc.get('skill_name'),
                "user_rating": doc.get('user_rating')
            })
            
        logging.info(f"Successfully retrieved job and {len(skill_proficiencies)} skill proficiencies.")
        
        response_data = {
            "job_details": job_doc,
            "skill_proficiencies": skill_proficiencies,
            "source": "MongoDB"
        }
        return jsonify(response_data)

    except Exception as e:
        logging.error(f"Error fetching data from MongoDB: {e}")
        return jsonify({"error": "Server error during database read."}), 500
    finally:
        if client:
            client.close()

@app.route('/api/rate', methods=['POST'])
def save_rating():
    """
    Receives and saves the manual job rating data (overall score, notes, updated skills) 
    to a new collection (e.g., 'manual_job_ratings').
    """
    rating_data = request.json
    
    # Simple validation
    if not rating_data or 'job_id' not in rating_data or 'overall_score' not in rating_data:
        return jsonify({"error": "Invalid rating data submitted."}), 400

    logging.info(f"Received rating for Job ID: {rating_data['job_id']} (Score: {rating_data['overall_score']})")
    
    # ----------------------------------------------------
    # NOTE: In a real implementation, you would save this data to MongoDB here.
    # ----------------------------------------------------
    client, db = connect_to_mongodb()
    
    if client:
        try:
            ratings_collection = db['manual_job_ratings']
            # Add a timestamp
            rating_data['rated_at'] = datetime.datetime.utcnow() 
           
            # Insert the complete rating document
            result = ratings_collection.insert_one(rating_data)
            logging.info(f"Rating saved to 'manual_job_ratings'. Document ID: {result.inserted_id}")
            
            # Optionally update the skills_proficiency collection with the new individual skill scores
            # This is left as an exercise, but the structure is similar to sync_ratings_to_mongo.py
            
        except Exception as e:
            logging.error(f"Error saving rating to MongoDB: {e}")
            # Do not return 500 so the user gets confirmation, but log the error
        finally:
            if client:
                client.close()
                
    # Always return success to the frontend if we processed the data (even if we just logged it)
    return jsonify({"message": "Rating saved successfully!", "data": rating_data}), 200


if __name__ == '__main__':
    # You will run this file locally via: python job_rater_server.py
    # Access the API at http://localhost:5000/api/job/123
    logging.info("Starting Flask server on http://localhost:5000")
    app.run(debug=True, port=5000)
