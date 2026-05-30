from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
from typing import List, Optional
import os
import io
import google.generativeai as genai
from pypdf import PdfReader

# 1. Start de FastAPI applicatie
app = FastAPI(title="AI for Fairer Dressage Judging")

# 2. Configureer de Google Gemini API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# 3. De Dressuurlogica (De 5 lagen)
class DressuurBeoordeling(BaseModel):
    oefening_naam: str
    ritme_score: float
    ontspanning_score: float
    aanleuning_score: float
    impuls_rechtgerichtheid: float
    verzameling_score: float
    feedback_milde_coach: str
    feedback_strenge_jury: str
    eindcijfer: float

# 4. HELPER FUNCTIE: Tekst uit de PDF van het protocol halen
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Zet de pagina's van het PDF-protocol om in kale tekst voor de AI gids."""
    pdf_file = io.BytesIO(file_bytes)
    reader = PdfReader(pdf_file)
    extracted_text = ""
    
    for page in reader.pages:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
            
    return extracted_text.strip()

# 5. Home route
@app.get("/")
def home():
    return {"status": "De AI Dressuur Jury backend draait succesvol!"}

# 6. DE INPUT ROUTE: Hier komen de Video URL én het PDF-bestand binnen
@app.post("/analyseer-proef/")
async def start_analyse(
    video_url: str, 
    judge_type: str, 
    protocol_file: UploadFile = File(...)
):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API sleutel ontbreekt op de server.")
    
    # Lees de bytes van het geüploade PDF-bestand
    try:
        file_bytes = await protocol_file.read()
        protocol_tekst = extract_text_from_pdf(file_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fout bij het lezen van het PDF-protocol: {str(e)}")
        
    # Controleer of we daadwerkelijk tekst hebben kunnen vinden in de PDF
    if not protocol_tekst:
        raise HTTPException(status_code=400, detail="Het PDF-bestand is leeg of kan niet worden gelezen.")

    # Voor nu sturen we een succesmelding terug met een klein stukje van de gelezen tekst als bewijs
    return {
        "status": "Succesvol ontvangen",
        "video_url": video_url,
        "jury_type": judge_type,
        "gids_protocol_naam": protocol_file.filename,
        "fragment_uit_gids": protocol_tekst[:150] + "..." # Toont de eerste 150 tekens van de proef ter controle
    }
