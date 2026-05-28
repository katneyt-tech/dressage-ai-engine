from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import os
import time

app = FastAPI()

# CORS Middleware toevoegen om "Failed to fetch" in de browser te voorkomen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

@app.post("/analyze")
async def analyze_ride(
    video: UploadFile = File(...),
    jury_type: str = Form("Gentle Judge"),
    dressage_test: str = Form("General Training")
):
    # Prompt met de proefnaam verwerkt
    prompt = f"""You are an expert dressage judge.
    Jury style: {jury_type}.
    Dressage test to evaluate: {dressage_test}.
    Analyze the provided video for technical accuracy based on the {dressage_test} requirements.
    Return the output in a clean JSON format.
    """

    model = genai.GenerativeModel('gemini-1.5-pro')
    video_file = genai.upload_file(video.file)
    
    # Wacht tot Gemini de video heeft verwerkt
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = genai.get_file(video_file.name)
    
    response = model.generate_content([prompt, video_file])
    return {"result": response.text}
