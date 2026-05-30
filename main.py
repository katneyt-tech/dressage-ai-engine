import os
import time
import requests
import tempfile
import io
import pypdf
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Query

# 1. Initialiseer de FastAPI applicatie
app = FastAPI(
    title="Dressuur AI API",
    description="Plak de links naar de video en de proef-PDF om de analyse te starten.",
    version="1.5.0"
)

# 2. Configureer de API-sleutel (werkt direct met je nieuwe AQ.-sleutel via de moderne SDK)
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
    proef: str = Query(..., description="De URL/link naar de dressuurproef PDF (bijv. de link naar je 40.pdf)")
):
    """
    Analyseer een dressuurvideo op basis van een video-URL en een proef-PDF-URL.
    """
    if not API_KEY:
        raise HTTPException(
            status_code=500, 
            detail="API-sleutel ontbreekt op de server. Controleer je Render instellingen."
        )

    temp_video_path = None
    video_file = None

    try:
        # Stap A: Download de proef-PDF en haal automatisch de tekst eruit
        print(f"Start download van proef-PDF: {proef}")
        pdf_response = requests.get(proef)
        if pdf_response.status_code != 200:
            raise Exception(f"Kan de proef-PDF niet downloaden via de link. HTTP Status: {pdf_response.status_code}")
        
        try:
            pdf_file = io.BytesIO(pdf_response.content)
            reader = pypdf.PdfReader(pdf_file)
            proef_tekst = ""
            for page in reader.pages:
                proef_tekst += page.extract_text() or ""
            
            if not proef_tekst.strip():
                raise Exception("De PDF is gelezen maar bevat geen bruikbare tekst.")
            print("Tekst succesvol uit de proef-PDF geëxtraheerd.")
        except Exception as pdf_err:
            raise Exception(f"Fout bij het verwerken van de PDF-inhoud: {str(pdf_err)}")

        # Stap B: Download de video via de 'link' parameter
        print(f"Start download van video: {link}")
        video_response = requests.get(link, stream=True)
        if video_response.status_code != 200:
            raise Exception(f"Kan video niet downloaden via de opgegeven link. HTTP Status: {video_response.status_code}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in video_response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_video_path = temp_file.name
        print("Video tijdelijk lokaal opgeslagen op server.")

        # Stap C: Upload de video naar Google Gemini via de moderne methode
        print("Video wordt geüpload naar Google Gemini...")
        video_file = genai.upload_file(path=temp_video_path)

        # Stap D: Wacht live tot Google klaar is met verwerken
        while video_file.state.name == "PROCESSING":
            print("Google verwerkt de video momenteel...")
            time.sleep(5)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise Exception("De video-verwerking is aan de kant van Google mislukt.")

        print("Video succesvol verwerkt. AI-analyse start nu...")

        # Stap E: Initialiseer het model (Gemini 1.5 Flash)
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")

        # Stap F: Combineer jury en de automatisch uitgelezen proef_tekst in de opdracht
        prompt = (
            f"Instructie/Rol van de jury: {jury}\n\n"
            f"Beoordeel de bijgevoegde video strikt op basis van deze dressuurproef richtlijnen:\n{proef_tekst}\n\n"
            "Geef een score en constructieve feedback per onderdeel in een nette, overzichtelijke structuur."
        )

        # Stap G: Start de analyse
        analysis_response = model.generate_content([video_file, prompt])
        print("Analyse voltooid!")
        
        return {
            "status": "Succes",
            "analyse": analysis_response.text
        }

    except Exception as e:
        print(f"Fout tijdens proces: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fout tijdens de AI-analyse: {str(e)}")

    finally:
        # Stap H: Altijd netjes opruimen om vollopen van de server en Google Cloud te voorkomen
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except Exception as e:
                print(f"Kon tijdelijk bestand niet verwijderen: {str(e)}")
        
        if video_file:
            try:
                genai.delete_file(video_file.name)
            except Exception as e:
                print(f"Kon Google-bestand niet wissen: {str(e)}")
