import os

def get_unique_filename(base_filename):
    """
    Checks if a file exists and appends a numeric suffix (e.g., _1, _2)
    to the filename until a unique name is found.
    
    Args:
        base_filename (str): The initial filename (e.g., 'report.csv').

    Returns:
        str: A unique filename (e.g., 'report_1.csv').
    """
    if not os.path.exists(base_filename):
        return base_filename

    name, ext = os.path.splitext(base_filename)
    counter = 1
    new_filename = f"{name}_{counter}{ext}"
    
    while os.path.exists(new_filename):
        counter += 1
        new_filename = f"{name}_{counter}{ext}"

    return new_filename
