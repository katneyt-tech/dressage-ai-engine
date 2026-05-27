from fastapi import FastAPI, UploadFile, File, Form
import google.generativeai as genai
import os

app = FastAPI()

# Jouw API-sleutel (Vervang door jouw echte sleutel in Render later)
genai.configure(api_key="AIzaSyAgEQjHwPsuIZcrAv2QveHe-HM0hr_cpXA")

@app.post("/analyze")
async def analyze_ride(
    video: UploadFile = File(...),
    jury_type: str = Form("local") # Kan "local" of "international" zijn
):
    # Hier kiezen we de prompt
    if jury_type == "international":
        prompt = """Strict FEI judge* instructies: Act as an elite, strict FEI 5* Dressage Judge and Biomechanical Expert. 
Analyze the provided video using the written protocol as your chronological guide.

You are known for your uncompromising and rigorous judging standards. To ensure absolute objectivity and fairness, apply the following strict scoring rules:

1. **Base Score (Maximum 10)**: Every movement starts at 10, but deductions must be applied strictly for any biomechanical flaw.
2. **Strict Deductions**:
    - **Behind the Vertical (Achter de loodlijn)**: If the horse's nose line drops behind the vertical even slightly, cap the maximum possible score for that movement at a 6.0.
    - **Rhythm/Tempo Mistakes (Tactfouten)**: Any irregularity in the 2-beat (trot), 3-beat (canter), or 4-beat (walk) must immediately result in a maximum score of 5.0 for that movement.
    - **Lack of Engagement (Onvoldoende ondertreden)**: If the hind legs do not clearly step into or over the prints of the front legs during extended movements, deduct at least 1.5 points.
    - **Contact/Submission (Aanleuning)**: Note any open mouth, tossing of the head, or tension, and deduct accordingly.
3. **Justification**: For every score below an 8.0, you MUST provide the exact timestamp and the objective, visual reason for the deduction.

Return the output in a structured JSON format for my app dashboard:
{
  "movement": string,
  "timestamp": string,
  "raw_metrics": {
    "rhythm_consistent": boolean,
    "head_position": "on_vertical" | "behind_vertical" | "above_vertical"
  },
  "strict_score": float,
  "judge_comments_critique": string
}
"""
    else:
        prompt = """Gentle jury: Act as a supportive, encouraging Local/National Dressage Judge and Trainer. 
Analyze the provided video using the written protocol as your guide.

Your goal is to help the rider improve while judging fairly but constructively. Use the following guidelines:

1. **Constructive Scoring**: Judge according to national standards. Be fair, but do not overly penalize minor loss of balance or brief moments behind the vertical.
2. **Positive Reinforcement**: For every movement, highlight one thing the rider or horse did WELL (e.g., "Good activity", "Nice steady rhythm").
3. **Actionable Advice**: If a score is below 7.0, explain HOW the rider can fix it in training (e.g., "Keep the hands steady in the turn to improve the contact").

Return the output in a structured JSON format:
{
  "movement": string,
  "timestamp": string,
  "score": float,
  "positive_feedback": string,
  "tip_for_improvement": string
}
"""

    # Hier wordt de video naar Gemini gestuurd
    model = genai.GenerativeModel('gemini-1.5-pro')
    video_file = genai.upload_file(video.file)
    response = model.generate_content([prompt, video_file])
    
    return {"result": response.text}
