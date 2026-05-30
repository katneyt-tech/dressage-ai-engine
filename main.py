from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import google.generativeai as genai

# 1. Start de FastAPI applicatie
app = FastAPI(title="AI for Fairer Dressage Judging")

# 2. Configureer de Google Gemini API Key (deze stellen we straks in op Render)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# 3. HIER DEFINIËREN WE DE DRESSUURLOGICA (De 5 lagen uit jouw basisdocument)
class DressuurBeoordeling(BaseModel):
    oefening_naam: str          # Bijv. "A-C Binnenkomen in verzamelde draf"
    
    # De 5 Lagen van de Trainingsschaal (0.0 - 10.0)
    ritme_score: float          # Takt, regelmaat, constante cadans
    ontspanning_score: float    # Ruggebruik, losgelatenheid, geen spanning
    aanleuning_score: float     # Stabiele verbinding, niet achter de loodlijn
    impuls_rechtgerichtheid: float # Energie vanuit het achterbeen, recht zijn
    verzameling_score: float    # Gewicht op de achterhand, elevatie
    
    # De Jury Switcher output
    feedback_milde_coach: str   # Opbouwende tips gericht op de hulpen van de ruiter
    feedback_strenge_jury: str  # Strikte FEI-reglementaire beoordeling (aftrek voor fouten)
    
    # Het uiteindelijke cijfer voor dit specifieke onderdeel
    eindcijfer: float

# 4. Een simpele 'Check' route om te kijken of je backend live staat op Render
@app.get("/")
def home():
    return {"status": "De AI Dressuur Jury backend draait succesvol!"}

# 5. De basis-route waar FlutterFlow straks de video en het protocol naartoe stuurt
@app.post("/analyseer-proef/")
def start_analyse(video_url: str, judge_type: str):
    # Hier komt in de volgende stap de koppeling met Gemini
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API sleutel ontbreekt.")
        
    return {
        "bericht": "Video ontvangen", 
        "video": video_url, 
        "jury_type": judge_type
    }
