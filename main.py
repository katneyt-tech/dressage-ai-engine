import os
import time
import requests
import tempfile
import io
import pypdf
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, UploadFile, File

# Eerst de applicatie initialiseren
app = FastAPI(title="Dressuur AI API", version="2.3.0")

# API Key ophalen
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

def get_flash_model_name():
    # Directe link naar de stabiele 3.5-flash voor jouw account
    return "models/gemini-3.5-flash"

@app.get("/")
def home():
    return {"status": "Online", "version": "2.3.0"}

@app.post("/analyseer")
async def analyseer_video(
    link: str = Query(..., description="Google Drive link naar de video"),
    jury: Literal["mild", "FEI"] = Query(..., description="Type jurering"),
    proef_pdf: UploadFile = File(..., description="Upload hier de PDF-proef")
):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API-sleutel ontbreekt.")

    try:
        # 1. PDF verwerken
        pdf_content = await proef_pdf.read()
        reader = pypdf.PdfReader(io.BytesIO(pdf_content))
        proef_tekst = "".join([page.extract_text() or "" for page in reader.pages])
        
        # 2. Video downloaden
        directe_url = link.replace("/view?usp=sharing", "").replace("file/d/", "uc?export=download&id=")
        video_res = requests.get(directe_url, stream=True)
        if video_res.status_code != 200:
            raise Exception(f"Video download mislukt. Status: {video_res.status_code}")
             
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            for chunk in video_res.iter_content(8192): tmp.write(chunk)
            temp_path = tmp.name

        # 3. Upload naar Gemini
        headers = {"X-Goog-Api-Key": API_KEY}
        init_res = requests.post("https://generativelanguage.googleapis.com/upload/v1beta/files", 
                                 headers={**headers, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "Content-Type": "application/json"},
                                 json={"file": {"displayName": "video.mp4"}})
        
        upload_url = init_res.headers["X-Goog-Upload-URL"]
        with open(temp_path, "rb") as f:
            final_res = requests.post(upload_url, headers={**headers, "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize", "Content-Type": "video/mp4"}, data=f.read())
        
        file_uri = final_res.json()["file"]["uri"]

        # 4. Analyse met 3.5-flash
        model_name = get_flash_model_name()
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"fileData": {"fileUri": file_uri, "mimeType": "video/mp4"}}, 
                    {"text": f"Je bent een officiële dressuurjury. Jury stijl: {jury}. Analyseer deze video strikt op basis van de volgende proef-richtlijnen: {proef_tekst}"}
                ]
            }]
        }
        
        res = requests.post(url, json=payload).json()
        
        if "candidates" not in res:
            raise Exception(f"Google API gaf een fout terug: {res}")
            
        return {"analyse": res['candidates'][0]['content']['parts'][0]['text']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout: {str(e)}")
