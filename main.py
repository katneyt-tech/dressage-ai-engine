import os
import time
import requests
import tempfile
import io
import pypdf
from typing import Literal
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Query, UploadFile, File

# 1. Initialiseer de FastAPI applicatie
app = FastAPI(
    title="Dressuur AI API",
    description="Upload je PDF-proef rechtstreeks vanaf je apparaat en plak de video-link.",
    version="1.8.0"
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
    naar een directe downloadlink.
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
async def analyseer_video(
    link: str = Query(..., description="De Google Drive deellink van de video (.mp4)"),
    jury: Literal["mild", "FEI"] = Query(..., description="Kies het type jurering"),
    proef_pdf: UploadFile = File(..., description="Selecteer het PDF-bestand van de proef vanaf je computer/telefoon")
):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API-sleutel ontbreekt op de server.")

    temp_video_path = None
    video_file = None

    try:
        # Stap 1: Lees de geüploade PDF direct uit het geheugen
        print(f"Bestand ontvangen: {proef_pdf.filename}")
        pdf_content = await proef_pdf.read()
        
        pdf_file = io.BytesIO(pdf_content)
        reader = pypdf.PdfReader(pdf_file)
        proef_tekst = ""
        for page in reader.pages:
            proef_tekst += page.extract_text() or ""
        
        if not proef_tekst.strip():
            raise Exception("De geüploade PDF bevat geen leesbare tekst of is leeg.")
        print("Tekst succesvol uit de geüploade PDF gehaald.")

        # Stap 2: Download de video via de Drive link
        directe_video_url = zet_om_naar_directe_download(link)
        print(f"Video downloaden via: {directe_video_url}")
        
        video_response = requests.get(directe_video_url, stream=True)
        if video_response.status_code != 200:
            raise Exception(f"Kan video ikke downloaden. Controleer de Drive-rechten. Status: {video_response.status_code}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in video_response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_video_path = temp_file.name

        # Stap 3: Uploaden naar Google Gemini
        print("Video wordt geüpload naar Google Gemini...")
        video_file = genai.upload_file(path=temp_video_path)

        # Stap 4: Wachten op verwerking
        while video_file.state.name == "PROCESSING":
            print("Google verwerkt de video...")
            time.sleep(5)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise Exception("De video-verwerking is bij Google mislukt.")

        # Stap 5: Analyse uitvoeren via Flash
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
