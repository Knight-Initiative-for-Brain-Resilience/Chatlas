import json
import openai

from django.conf import settings
from django.http import StreamingHttpResponse
from ninja import Router

# Set OpenAI API key from settings
openai.api_key = settings.OPENAI_API_KEY

# Create API router
router = Router()

@router.get("/stream", tags=_TGS)
def create_stream(request):

    # Read user message from URL
    user_content = request.GET.get('content', '')

    # Generator that talks to OpenAI API
    def event_stream():
        for chunk in openai.ChatCompletion.create(
            model='gpt-4-turbo',
            messages=[{
                "role": "user",
                "content": f"{user_content}. \ 
                    Response should be in markdown formatting."
            }],
            stream=True,
        ):
            chatcompletion_delta = chunk["choices"][0].get("delta", {})
            data = json.dumps(dict(chatcompletion_delta))
            print(data)
            yield f'data: {data}\\n\\n'

    # Stream API output to browser in real-time
    response = StreamingHttpResponse(
        event_stream(), 
        content_type="text/event-stream"
    )

    response.headers.update({
        'X-Accel-Buffering': 'no',   # Disable buffering in nginx
        'Cache-Control': 'no-cache'  # Prevent caching
    })
    return response