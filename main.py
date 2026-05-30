import os
import time
import requests
import tempfile
from typing import Literal
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Query, Form

# 1. Initialiseer de FastAPI applicatie
app = FastAPI(
    title="Dressuur AI API",
    description="Plak de video-link, kies de jurering en plak de tekst van de proef.",
    version="1.7.0"
)

# 2. Configureer de API-sleutel
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
    print("Gemini SDK succesvol geconfigureerd.")
else:
    print("WAARSCHUWING: Geen API-sleutel gevonden!")

def zet_om_naar_directe_download(url: str) -> str:
    """
    Bouwt een standaard Google Drive deellink automatisch om 
    naar een directe downloadlink die de code kan lezen.
    """
    if "drive.google.com" in url:
        if "/file/d/" in url:
            file_id = url.split("/file/d/")[1].split("/")[0]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        elif "id=" in url:
            file_id = url.split("id=")[1].split("&")[0]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url

@app.get("/")
def home():
    return {"status": "Online", "message": "Ga naar /docs om de proef te starten."}

@app.post("/analyseer")
def analyseer_video(
    link: str = Query(..., description="De Google Drive deellink van de video (.mp4)"),
    jury: Literal["mild", "FEI"] = Query(..., description="Kies het type jurering uit het dropdown-menu"),
    proef_tekst: str = Query(..., description="Plak hier de volledige tekst of richtlijnen van de dressuurproef")
):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API-sleutel ontbreekt op de server.")

    temp_video_path = None
    video_file = None

    try:
        # Stap 1: Controleer of de proef_tekst niet leeg is
        if not proef_tekst.strip():
            raise Exception("Het veld 'proef_tekst' mag niet leeg zijn.")

        # Stap 2: Zet de video-URL om naar een directe download en start de download
        directe_video_url = zet_om_naar_directe_download(link)
        print(f"Video downloaden via: {directe_video_url}")
        
        video_response = requests.get(directe_video_url, stream=True)
        if video_response.status_code != 200:
            raise Exception(f"Kan video niet downloaden. Staat de Google Drive link op 'Iedereen met de link'? Status: {video_response.status_code}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in video_response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_video_path = temp_file.name

        # Stap 3: Uploaden naar Google Gemini (Flash is stabiel voor grote video's)
        print("Video wordt geüpload naar Google Gemini...")
        video_file = genai.upload_file(path=temp_video_path)

        # Stap 4: Wachten op verwerking door Google
        while video_file.state.name == "PROCESSING":
            print("Google verwerkt de video...")
            time.sleep(5)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise Exception("De video-verwerking is bij Google mislukt.")

        # Stap 5: Analyse uitvoeren
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")

        prompt = (
            f"Je bent een officiële dressuurjury en je jureert strikt volgens de {jury.upper()}-richtlijnen.\n"
            f"Beoordeel de video nauwkeurig op basis van deze proef:\n{proef_tekst}\n\n"
            f"Geef feedback die past bij een {jury} jurering, inclusief scores per onderdeel in een nette structuur."
        )

        analysis_response = model.generate_content([video_file, prompt])
        
        return {
            "status": "Succes",
            "jury_stijl": jury,
            "analyse": analysis_response.text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout tijdens de AI-analyse: {str(e)}")

    finally:
        # Stap 6: Netjes opruimen
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except:
                pass
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except:
                pass
