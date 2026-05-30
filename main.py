import os
import time
import requests
import tempfile
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Query

# 1. Initialiseer de FastAPI applicatie
app = FastAPI(
    title="Dressuur AI API",
    description="Alle invoervelden staan nu gegarandeerd direct onder de Parameters.",
    version="1.4.0"
)

# 2. Configureer de API-sleutel (werkt met je AQ.-sleutel via de moderne SDK)
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
    print("Gemini SDK succesvol geconfigureerd.")
else:
    print("WAARSCHUWING: Geen API-sleutel gevonden in de omgevingsvariabelen!")

@app.get("/")
def home():
    return {
        "status": "Online", 
        "message": "De Dressuur AI API draait. Ga naar /docs om de parameters in te vullen."
    }

@app.post("/analyseer")
def analyseer_video(
    link: str = Query(..., description="De direct downloadbare URL van de video (.mp4)"),
    jury: str = Query(..., description="De rol of instructie voor de jury (bijv. 'Je bent een subtop jury')"),
    proef: str = Query(..., description="De volledige tekst of richtlijnen van de dressuurproef")
):
    """
    Analyseer een dressuurvideo op basis van de ingevoerde parameters.
    """
    if not API_KEY:
        raise HTTPException(
            status_code=500, 
            detail="API-sleutel ontbreekt op de server. Controleer je Render instellingen."
        )

    temp_video_path = None
    video_file = None

    try:
        # Stap A: Download de video via de 'link' parameter
        print(f"Start download van video: {link}")
        response = requests.get(link, stream=True)
        if response.status_code != 200:
            raise Exception(f"Kan video niet downloaden via de opgegeven link. Status: {response.status_code}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_video_path = temp_file.name
        print("Video tijdelijk opgeslagen op server.")

        # Stap B: Upload de video naar Google Gemini via de moderne methode
        print("Video wordt geüpload naar Google Gemini...")
        video_file = genai.upload_file(path=temp_video_path)

        # Stap C: Wacht live tot Google klaar is met verwerken
        while video_file.state.name == "PROCESSING":
            print("Google verwerkt de video momenteel...")
            time.sleep(5)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise Exception("De video-verwerking is aan de kant van Google mislukt.")

        print("Video succesvol verwerkt. AI-analyse start nu...")

        # Stap D: Initialiseer het model (Gemini 1.5 Flash)
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")

        # Stap E: Combineer jury en proef invoer in de opdracht
        prompt = (
            f"Instructie/Rol van de jury: {jury}\n\n"
            f"Beoordeel de bijgevoegde video strikt op basis van deze dressuurproef:\n{proef}\n\n"
            "Geef een score en constructieve feedback per onderdeel in een nette structuur."
        )

        # Stap F: Start de analyse
        analysis_response = model.generate_content([video_file, prompt])
        print("Analyse voltooid!")
        
        return {
            "status": "Succes",
            "analyse": analysis_response.text
        }

    except Exception as e:
        print(f"Fout: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fout tijdens de AI-analyse: {str(e)}")

    finally:
        # Stap G: Altijd netjes opruimen om vollopen te voorkomen
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except Exception as e:
                print(f"Kon tijdelijk bestand ikke verwijderen: {str(e)}")
        
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except Exception as e:
                print(f"Kon Google-bestand niet wissen: {str(e)}")
