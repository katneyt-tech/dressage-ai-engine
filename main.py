from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import os
import time

app = FastAPI()

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
    # De prompt dwingt de AI nu om te denken vanuit de Skala der Ausbildung
    # Dit garandeert de kwaliteit van de beoordeling
    if jury_type == "Strict FEI Judge":
        prompt = f"""You are an elite, FEI 5* Dressage Judge.
Evaluate the video for the dressage test: {dressage_test}.
Your judgment MUST be based on the 'Skala der Ausbildung' (Rhythm, Suppleness, Contact, Impulsion, Straightness, Collection).

STRICT SCORING RULES:
1. Base score starts at 10. Deduct immediately for loss of rhythm or biomechanical errors.
2. Nose behind the vertical = Capped at 6.0.
3. Tact/Rhythm irregularity = Capped at 5.0.
4. If hindlegs do not track up/into the center of gravity, deduct 1.5 points.

Output must be a valid JSON:
{{
  "movement": string,
  "timestamp": string,
  "score": float,
  "technical_critique": "Focus on Skala der Ausbildung: rhythm, contact, and biomechanics",
  "reasoning": "Objective observation of the horse's silhouette and gaits"
}}"""
    else:
        prompt = f"""You are a supportive, high-level Dressage Trainer.
Evaluate the video for the dressage test: {dressage_test}.
Your goal is to improve the rider and horse's biomechanical harmony.

GUIDELINES:
1. Focus on the progression of training (Skala der Ausbildung).
2. Give positive feedback on what is going well.
3. Provide actionable, classical dressage training advice to correct flaws in rhythm or contact.

Output must be a valid JSON:
{{
  "movement": string,
  "timestamp": string,
  "score": float,
  "positive_reinforcement": string,
  "actionable_training_advice": "Specific exercises to improve this movement"
}}"""

    model = genai.GenerativeModel('gemini-1.5-pro')
    video_file = genai.upload_file(video.file)
    
    # Wacht tot de verwerking klaar is
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = genai.get_file(video_file.name)
        
    response = model.generate_content([prompt, video_file])
    
    return {"result": response.text}
