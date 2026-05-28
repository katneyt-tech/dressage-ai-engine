from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import os
import time

app = FastAPI()

# CORS-instellingen om communicatie met je app/browser mogelijk te maken
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
    # Logica voor de Strict Jury met al jouw originele instructies
    if jury_type == "Strict FEI Judge":
        prompt = f"""Act as an elite, strict FEI 5* Dressage Judge and Biomechanical Expert. 
You are evaluating the dressage test: {dressage_test}.

You are known for your uncompromising and rigorous judging standards. To ensure absolute objectivity and fairness, apply the following strict scoring rules:

1. **Base Score (Maximum 10)**: Every movement starts at 10, but deductions must be applied strictly for any biomechanical flaw.
2. **Strict Deductions**:
    - **Behind the Vertical**: If the horse's nose line drops behind the vertical even slightly, cap the maximum possible score for that movement at a 6.0.
    - **Rhythm/Tempo Mistakes**: Any irregularity in the 2-beat (trot), 3-beat (canter), or 4-beat (walk) must immediately result in a maximum score of 5.0 for that movement.
    - **Lack of Engagement**: If the hind legs do not clearly step into or over the prints of the front legs during extended movements, deduct at least 1.5 points.
    - **Contact/Submission**: Note any open mouth, tossing of the head, or tension, and deduct accordingly.
3. **Justification**: For every score below an 8.0, you MUST provide the exact timestamp and the objective, visual reason for the deduction.

Return the output in a structured JSON format:
{{
  "movement": string,
  "timestamp": string,
  "raw_metrics": {{
    "rhythm_consistent": boolean,
    "head_position": "on_vertical" | "behind_vertical" | "above_vertical"
  }},
  "strict_score": float,
  "judge_comments_critique": string
}}"""
    
    # Logica voor de Gentle Jury met al jouw originele instructies
    else:
        prompt = f"""Act as a supportive, encouraging Local/National Dressage Judge and Trainer.
You are evaluating the dressage test: {dressage_test}.

Your goal is to help the rider improve while judging fairly but constructively. Use the following guidelines:

1. **Constructive Scoring**: Judge according to national standards. Be fair, but do not overly penalize minor loss of balance or brief moments behind the vertical.
2. **Positive Reinforcement**: For every movement, highlight one thing the rider or horse did WELL (e.g., "Good activity", "Nice steady rhythm").
3. **Actionable Advice**: If a score is below 7.0, explain HOW the rider can fix it in training (e.g., "Keep the hands steady in the turn to improve the contact").

Return the output in a structured JSON format:
{{
  "movement": string,
  "timestamp": string,
  "score": float,
  "positive_feedback": string,
  "tip_for_improvement": string
}}"""

    # Verwerking door Gemini
    model = genai.GenerativeModel('gemini-1.5-pro')
    video_file = genai.upload_file(video.file)
    
    # Wacht tot de video verwerkt is
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = genai.get_file(video_file.name)
        
    response = model.generate_content([prompt, video_file])
    
    return {"result": response.text}
