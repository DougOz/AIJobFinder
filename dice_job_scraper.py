import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

def scrape_dice_job(url):
    """
    Scrapes a single job posting from Dice.com and returns a dictionary
    containing the job details.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        #print(f"Fetching URL: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Selectors for job details
        title_element = soup.select_one('[data-cy="jobTitle"]')
        company_element = soup.select_one('[data-cy="companyNameLink"]')
        location_element = soup.select_one('[data-cy="location"]')
        description_element = soup.select_one('#jobDescription')
        job_type_elements = soup.select('[data-cy="locationDetails"] span')
        
        # --- NEW: Corrected selector for skills list ---
        # Select all <span> tags within the div that has the data-cy="skillsList" attribute.
        skills_elements = soup.select('div[data-cy="skillsList"] span')
        
        salary_element = soup.select_one('[data-cy="payDetails"] span')
        posted_date_element = soup.select_one('meta[property="og:publish_date"]')
        dates_element = soup.select_one('[data-cy="postedDate"]')
        
        # Extract and clean data
        title = title_element.get_text(strip=True) if title_element else 'N/A'
        company = company_element.get_text(strip=True) if company_element else 'N/A'
        location = location_element.get_text(strip=True) if location_element else 'N/A'
        description = description_element.get_text(strip=False) if description_element else 'N/A'
        posted_date = posted_date_element['content'] if posted_date_element else 'N/A'
        
        # Extract updated date text using string manipulation
        updated_date = 'N/A'
        if dates_element:
            dates_text = dates_element.get_text(strip=True)
            if '|' in dates_text:
                parts = dates_text.split('|')
                updated_date = parts[1].strip().replace('Updated ', '').strip()
        
        # Extract job type, skills, and salary if they exist.
        job_types = [span.get_text(strip=True) for span in job_type_elements]
        skills = [span.get_text(strip=True) for span in skills_elements]
        salary = salary_element.get_text(strip=True) if salary_element else 'N/A'
        
        # Add the URL and current date/time to the output dictionary
        job_details = {
            'url': url,
            'current_datetime': datetime.now().isoformat(),
            'title': title,
            'company': company,
            'location': location,
            'posted_date': posted_date,
            'updated_date': updated_date,
            'job_types': job_types,
            'salary': salary,
            'skills': skills,
            'description': description
            #'description': ' '.join(description.split())
        }
        
        return job_details

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None
    except Exception as e:
        print(f"An error occurred during scraping: {e}")
        return None

if __name__ == "__main__":
    # Example URL for a Dice job posting
    dice_url = "https://www.dice.com/job-detail/f0618b89-21f4-4345-8187-cba96ad70903"
    
    job_info = scrape_dice_job(dice_url)

    if job_info:
        print("\n--- Job Details ---")
        for key, value in job_info.items():
            if key == 'description':
                print(f"{key.capitalize()}: {value[:300]}...")
            elif key == 'skills' or key == 'job_types':
                print(f"{key.capitalize()}: {', '.join(value)}")
            else:
                print(f"{key.capitalize()}: {value}")
    else:
        print("Failed to scrape job details.")