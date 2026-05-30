import os
import time
import requests
import tempfile
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# 1. Initialiseer de FastAPI applicatie
app = FastAPI(
    title="Dressuur AI Beoordeling API",
    description="Een moderne API voor het objectief beoordelen van dressuurproeven met Gemini 1.5",
    version="1.1.0"
)

# 2. Configureer de API-sleutel (zoekt naar GOOGLE_API_KEY of de oude API_KEY naam)
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
    print("Gemini SDK succesvol geconfigureerd met de API-sleutel.")
else:
    print("WAARSCHUWING: Er is geen API-sleutel gevonden in de Render omgevingsvariabelen!")

# 3. Definieer het input-model voor Swagger (/docs)
class BeoordelingRequest(BaseModel):
    video_url: str
    pdf_tekst: str

@app.get("/")
def home():
    """Eenvoudige gezondheidscheck voor Render."""
    return {
        "status": "Online", 
        "message": "De Dressuur AI API draait succesvol! Ga naar /docs voor de interface."
    }

@app.post("/analyseer")
def analyseer_video(request: BeoordelingRequest):
    """
    Downloadt een video vanaf een URL, uploadt deze naar Gemini 1.5
    en analyseert de beelden op basis van de meegegeven PDF-tekst.
    """
    if not API_KEY:
        raise HTTPException(
            status_code=500, 
            detail="API-sleutel ontbreekt op de server. Controleer je Render Environment instellingen."
        )

    temp_video_path = None
    video_file = None

    try:
        # Stap A: Download de video vanaf de URL naar een tijdelijk lokaal bestand
        print(f"Start download van video: {request.video_url}")
        response = requests.get(request.video_url, stream=True)
        if response.status_code != 200:
            raise Exception(f"Kan video niet downloaden. HTTP Status: {response.status_code}")

        # Maak een veilig tijdelijk bestand aan op de Render-server
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_video_path = temp_file.name
        print(f"Video succesvol lokaal opgeslagen op: {temp_video_path}")

        # Stap B: Upload de video naar Google Gemini met de moderne upload_file methode
        print("Video wordt geüpload naar Google Gemini...")
        video_file = genai.upload_file(path=temp_video_path)
        print(f"Upload voltooid. Google Bestands-ID: {video_file.name}")

        # Stap C: Wacht live tot Google klaar is met het verwerken van de video
        while video_file.state.name == "PROCESSING":
            print("Google verwerkt de video momenteel... 5 seconden geduld...")
            time.sleep(5)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise Exception("De video-verwerking is aan de kant van Google mislukt.")

        print("Video is succesvol verwerkt door Google. AI-analyse wordt gestart...")

        # Stap D: Initialiseer het model (Gemini 1.5 Flash is razendsnel met video)
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")

        # Stap E: Bouw de instructie (prompt) voor de AI
        prompt = (
            "Je bent een professionele, objectieve dressuurjury.\n"
            "Beoordeel de bijgevoegde video strikt op basis van de volgende proefrichtlijnen:\n\n"
            f"{request.pdf_tekst}\n\n"
            "Geef een duidelijke beoordeling per onderdeel met een score en constructieve feedback. "
            "Zorg dat het resultaat netjes geformatteerd is (bij voorkeur als een valide JSON-structuur)."
        )

        # Stap F: Start de daadwerkelijke AI-analyse
        analysis_response = model.generate_content([video_file, prompt])
        print("Analyse succesvol afgerond!")
        
        return {
            "status": "Succes",
            "analyse": analysis_response.text
        }

    except Exception as e:
        print(f"CRITIEKE FOUT: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fout tijdens de AI-analyse: {str(e)}")

    finally:
        # Stap G: Altijd strikt opruimen (gebeurt ook bij fouten om vollopen van server te voorkomen)
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
            print("Tijdelijk lokaal videobestand succesvol verwijderd van Render.")
        
        if video_file:
            try:
                genai.delete_file(video_file.name)
                print("Videobestand succesvol opgeruimd uit Google Cloud opslag.")
            except Exception as e:
                print(f"Waarschuwing: Kon bestand niet wissen bij Google: {str(e)}")
