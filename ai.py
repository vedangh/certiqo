import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Tried in order. If one is busy or missing, the next is used.
MODELS = ["gemini-3.8-flash"]
RETRIES = 4


class AIUnavailable(Exception):
    pass


def draft_text(prompt: str) -> str:
    last_error = None
    for model in MODELS:
        for attempt in range(RETRIES):
            try:
                response = _client.models.generate_content(model=model, contents=prompt)
                return response.text
            except errors.ServerError as e:      # 5xx: busy or temporary
                last_error = e
                time.sleep(2 ** attempt)         # waits 1s, 2s, 4s, 8s
            except errors.ClientError as e:      # 4xx: wrong model, bad key, rate limit
                last_error = e
                break                            # retrying won't help, try next model
    raise AIUnavailable(f"AI service unavailable: {last_error}")
