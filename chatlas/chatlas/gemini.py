import google.generativeai as genai
import re

# Function: Browse web
def browse_web(query):
    
    # Set Gemini API key
    API_KEY = 'AIzaSyB_k8nF8dJYNcyd9jNi7u1XYy672ytq-5Y'
    genai.configure(api_key = API_KEY)

    # Set Gemini model
    model = genai.GenerativeModel('gemini-2.5-pro')

    # Generate Gemini response
    print("Browsing web...")
    response = model.generate_content(
        query + ". Give me the references for it with the links."
    )
    text = response.text
    
    # Clean input text
    clean_text = clean_markdown(text)
    return clean_text

# Function: Format markdown response
def clean_markdown(text):

    # Convert markdown bold headers to readable format with colon
    text = re.sub(r'\*\*([^*]+)\*\*', r'\n\n\1:\n', text)

    # Replace markdown list items, changing '*' to a dash '-'
    text = re.sub(r'\n\*', '\n -', text)

    # Extract URLs from markdown link syntax and format them nicely
    text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'\n\1: \2', text)

    # Remove excess newlines
    text = re.sub(r'\n{2,}', '\n\n', text)
    
    # Regular expression for matching URLs
    url_re = re.compile(
        r'(https?://[^\s]+)',
        re.IGNORECASE
    )

    # Replace URLs with HTML anchor tag
    text = re.sub(url_re, r'<a href="\1" target="_blank">\1</a>', text)

    return text