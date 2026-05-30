from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
from typing import List, Optional
import os
import io
import json
import time
import httpx
import google.generativeai as genai
from pypdf import PdfReader

# 1. Start de FastAPI applicatie
app = FastAPI(title="AI for Fairer Dressage Judging")

# 2. Configureer de Google Gemini API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# 3. Het Pydantic-model voor de output
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

class ProefResultaat(BaseModel):
    totaal_percentage: float
    beoordeling_per_oefening: List[DressuurBeoordeling]

# 4. HELPER FUNCTIE: Tekst uit de PDF halen
def extract_text_from_pdf(file_bytes: bytes) -> str:
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

# 6. DE HOOFDROUTE: Nu met volwaardige Video Ingest
@app.post("/analyseer-proef/", response_model=ProefResultaat)
async def start_analyse(
    video_url: str, 
    judge_type: str, 
    protocol_file: UploadFile = File(...)
):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API sleutel ontbreekt op de server.")
    
    # A. PDF tekst extraheren (De Gids)
    try:
        file_bytes = await protocol_file.read()
        protocol_tekst = extract_text_from_pdf(file_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fout bij het lezen van de PDF: {str(e)}")
        
    if not protocol_tekst:
        raise HTTPException(status_code=400, detail="Het PDF-protocol bevat geen leesbare tekst.")

    # B. Video downloaden naar de backend
    tijdelijk_video_pad = "tijdelijke_video.mp4"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url, timeout=60.0)
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Kan de video niet downloaden van de opgegeven URL.")
            with open(tijdelijk_video_pad, "wb") as f:
                f.write(response.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout bij downloaden video: {str(e)}")

    # C. Video uploaden naar Google Gemini Files API
    try:
        print("Video uploaden naar Gemini...")
        gemini_file = genai.upload_file(path=tijdelijk_video_pad)
        
        # Wacht tot Google de video heeft verwerkt (essentieel voor video's)
        while gemini_file.state.name == "PROCESSING":
            print("Gemini verwerkt de video momenteel...")
            time.sleep(3)
            gemini_file = genai.get_file(gemini_file.name)
            
        if gemini_file.state.name == "FAILED":
            raise HTTPException(status_code=500, detail="Google Gemini kon de video niet verwerken.")
            
        print("Video succesvol verwerkt door Gemini. Start jurering...")

        # D. De Systeeminstructie ('De Gouden Prompt')
        systeem_instructie = (
            "Je bent een gecertificeerde FEI 5* Dressuurjury en een professionele dressuurruiter. "
            "Jouw taak is om de gereden dressuurvideo objectief te beoordelen op basis van het officiële proef-protocol. "
            "Je gebruikt de 'Gids-methode': je volgt exact de oefeningen zoals beschreven in het onderstaande protocol.\n\n"
            f"--- HET OFFICIËLE PROTOCOL (DE GIDS) ---\n{protocol_tekst}\n"
            "-----------------------------------------\n\n"
            "Beoordeel ELKE oefening uit het protocol op basis van de 5 lagen van de Klassieke Trainingsschaal:\n"
            "1. Ritme & Regelmaat (takt, constante cadans)\n"
            "2. Ontspanning (ruggebruik, losgelatenheid, afwezigheid van conflictgedrag zoals staartzwiepen of open mond)\n"
            "3. Aanleuning (stabiele verbinding, nek als hoogste punt, absoluut NIET achter de loodlijn)\n"
            "4. Impuls & Rechtgerichtheid (energie vanuit de achterhand, achterbenen volgen de voorbenen)\n"
            "5. Verzameling (gewichtsverplaatsing naar de achterhand, elevatie vanuit de schoft)\n\n"
            "Geef per laag een score tussen 0.0 i.p.v. 10.0. "
            "Bereken het 'eindcijfer' voor de oefening als het wiskundige gemiddelde van deze 5 lagen.\n\n"
            "Schrijf voor ELKE oefening twee types feedback:\n"
            "- feedback_milde_coach: Opbouwende, motiverende tips gericht op de rijtechnische hulpen van de ruiter.\n"
            "- feedback_strenge_jury: Strikte, reglementaire FEI-beoordeling, objectief en direct.\n\n"
            "Je MOET antwoorden in een strikt JSON-formaat dat exact matcht met de gevraagde structuur."
        )

        # E. De AI aanroepen met de ECHTE video en de prompt
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro",
            generation_config={"response_mime_type": "application/json"}
        )
        
        gebruiker_prompt = f"Analyseer deze dressuurvideo in de modus: {judge_type}. Geef de volledige JSON terug."
        
        # We sturen nu het daadwerkelijke video-object van Google mee!
        response = model.generate_content([gemini_file, systeem_instructie, gebruiker_prompt])
        
        # F. Resultaat verwerken
        resultaat_json = json.loads(response.text)
        return resultaat_json

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Gemini leverde geen geldige JSON-structuur.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout tijdens de AI-analyse: {str(e)}")
    finally:
        # Altijd de tijdelijke video opruimen op de server
        if os.path.exists(tijdelijk_video_pad):
            os.remove(tijdelijk_video_pad)
        try:
            # Verwijder de video ook uit de cloudomgeving van Google
            genai.delete_file(gemini_file.name)
        except:
            pass
