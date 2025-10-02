from urllib.parse import urlencode, quote_plus

def build_dice_url(search_text, location=None, workplace_type=None):
    """
    Builds a Dice.com job search URL based on provided parameters,
    with a specific order for the query parameters.

    Args:
        search_text (str): The primary search query (e.g., "software engineer").
        location (str, optional): The location for the search (e.g., "New York, NY").
                                  The country code ", USA" will be appended automatically.
                                  Defaults to None.
        workplace_type (str, optional): The type of work environment. Valid options are:
                                        "remote", "hybrid", "onsite", or None for any.
                                        Case-insensitive. Defaults to None.

    Returns:
        str: The complete, formatted URL for the Dice job search.
    """
    # Base URL for all Dice job searches
    base_url = "https://www.dice.com/jobs?"
    
    # List to hold the query parameters in the desired order
    ordered_params = []
    
    # Handle the workplace type filter first, if provided
    if workplace_type:
        workplace_type_map = {
            'remote': 'Remote',
            'hybrid': 'Hybrid',
            'onsite': 'Onsite'
        }
        mapped_type = workplace_type_map.get(workplace_type.lower())
        if mapped_type:
            ordered_params.append(('filters.workplaceTypes', mapped_type))

    # Add location next, if provided, and append the country code
    if location:
        full_location = f"{location}, USA"
        ordered_params.append(('location', full_location))
        
    # Add the primary search text last
    if search_text:
        ordered_params.append(('q', search_text))

    # URL-encode the ordered parameters and build the final URL
    query_string = urlencode(ordered_params, quote_via=quote_plus)
    full_url = f"{base_url}{query_string}"
    
    return full_url

if __name__ == '__main__':
    # --- Examples of how to use the function ---
    
    # 1. A basic search for "software engineer"
    url1 = build_dice_url(search_text="software engineer")
    print(f"Basic search URL: {url1}")
    
    # 2. Search for "data scientist" in "San Francisco, CA"
    url2 = build_dice_url(search_text="data scientist", location="San Francisco, CA")
    print(f"Location-based search URL: {url2}")
    
    # 3. Search for "remote" "full stack developer" jobs
    url3 = build_dice_url(search_text="full stack developer", workplace_type="remote")
    print(f"Remote search URL: {url3}")
    
    # 4. Search for "Python developer" with all parameters
    url4 = build_dice_url(
        search_text="Python developer",
        location="Austin, TX",
        workplace_type="hybrid"
    )
    print(f"All parameters URL: {url4}")
