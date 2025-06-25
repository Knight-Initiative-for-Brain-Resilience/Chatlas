#########################
### ENVIRONMENT SETUP ###
#########################

# Import modules
import json
import nltk

from django.http import JsonResponse
from django.shortcuts import render
from .gemini import browse_web
from .functions import chat
from nltk.tokenize import word_tokenize

# Download punkt for word_tokenize
nltk.download('punkt', quiet=True)

####################
### UI FUNCTIONS ###
####################

# Function: Renders landing page
def index(request):
    return render(request, 'chatlas/index.html')

########################
### HELPER FUNCTIONS ###
########################

# Function: Parse user input
def parse_input(request):
    try:
        data = json.loads(request.body)
        user_input = data.get('message', '')
        if not user_input:
            raise ValueError("Missing 'message'.")
        return user_input
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON.")

# Function: Determine if web search requested
def search_requested(user_input):
    user_input = set(word_tokenize(user_input.lower()))
    search_words = {'search', 'find', 'lookup', 'google', 'web search'}
    return 'web_search' if user_input & search_words else 'chat'

# Function: Generate response to user request
def process_input(user_input, history):
    if search_requested(user_input) == 'web_search':
        content = browse_web(user_input)
    else:
        content, history = chat(user_input, history)
    return content, history

# Function: Formats JSON as graph or text for response
def build_response(content):
    return JsonResponse({"response": content})
        
##########################
### MAIN CHAT FUNCTION ###
##########################

# Function: API endpoint for chat
def api_chat(request):
    try:
        # Parse user input
        user_input = parse_input(request)
        print(f"Received message: {user_input}")

        # Load history and process request
        history = request.session.get('history', [])
        content, history = process_input(user_input, history)
        
        # Update history
        request.session['history'] = history

        # Return formatted response
        return build_response(content)

    # Handle errors
    except ValueError as e:
        print(f"Input error: {e}")
        return JsonResponse({"error": str(e)}, status=400)

    except Exception as e:
        print(f"Error in api_chat: {e}")
        return JsonResponse({"error": str(e)}, status=500)