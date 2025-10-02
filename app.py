from flask import Flask, request, jsonify
from flask_cors import CORS
from dice_scraper import scrape_dice_job

# Initialize the Flask application
app = Flask(__name__)
# Enable CORS for all routes, allowing the frontend to access the server
CORS(app)

@app.route('/scrape_job', methods=['POST'])
def scrape_job():
    """
    Receives a URL from the frontend, scrapes the job details, and returns them as JSON.
    """
    # Check if the request body is valid JSON
    if not request.json or 'url' not in request.json:
        return jsonify({"error": "Invalid request. Please provide a 'url' in the JSON body."}), 400

    url = request.json['url']
    print(f"Received request to scrape URL: {url}")
    
    # Call the scraping function from dice_scraper.py
    job_data = scrape_dice_job(url)
    
    # Check if the scraper returned data or an error
    if job_data:
        print("Scraping successful. Returning job data.")
        return jsonify(job_data), 200
    else:
        print("Scraping failed. Returning an error.")
        return jsonify({"error": "Failed to scrape job details from the provided URL."}), 500

if __name__ == '__main__':
    # You need to install the following packages:
    # pip install Flask
    # pip install Flask-Cors
    # pip install beautifulsoup4
    # pip install requests
    
    # The debug=True flag automatically reloads the server on code changes
    # and provides helpful error messages.
    app.run(debug=True)
