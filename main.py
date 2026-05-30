import os
import time
import requests
import tempfile
import io
import pypdf
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, UploadFile, File

app = FastAPI(
    title="Dressuur AI API",
    description="Upload je PDF-proef rechtstreeks en plak de video-link.",
    version="1.9.0"
)

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

def zet_om_naar_directe_download(url: str) -> str:
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
    return {"status": "Online", "message": "API is live. Ga naar /docs"}

@app.post("/analyseer")
async def analyseer_video(
    link: str = Query(..., description="De Google Drive deellink van de video (.mp4)"),
    jury: Literal["mild", "FEI"] = Query(..., description="Kies het type jurering"),
    proef_pdf: UploadFile = File(..., description="Selecteer het PDF-bestand van de proef")
):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API-sleutel ontbreekt op de server.")

    try:
        # 1. Verwerk PDF
        pdf_content = await proef_pdf.read()
        pdf_file = io.BytesIO(pdf_content)
        reader = pypdf.PdfReader(pdf_file)
        proef_tekst = "".join([page.extract_text() or "" for page in reader.pages])
        
        if not proef_tekst.strip():
            raise Exception("De PDF bevat geen leesbare tekst.")

        # 2. Download Video naar tijdelijk bestand
        directe_video_url = zet_om_naar_directe_download(link)
        video_response = requests.get(directe_video_url, stream=True)
        if video_response.status_code != 200:
            raise Exception(f"Kan video niet downloaden via Drive. Status: {video_response.status_code}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in video_response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_video_path = temp_file.name

        # 3. Upload naar Gemini via pure HTTP (GEEN SDK meer, dus GEEN discovery fouten!)
        headers = {"X-Goog-Api-Key": API_KEY}
        
        # Stap A: Initialiseer de upload
        init_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        init_headers = {**headers, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "Content-Type": "application/json"}
        init_body = {"file": {"displayName": "dressuur_video.mp4"}}
        
        init_res = requests.post(init_url, headers=init_headers, json=init_body)
        upload_url = init_res.headers.get("X-Goog-Upload-URL")
        
        # Stap B: Upload de bytes
        with open(temp_video_path, "rb") as f:
            video_bytes = f.read()
        
        upload_headers = {**headers, "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize", "Content-Type": "video/mp4"}
        finish_res = requests.post(upload_url, headers=upload_headers, data=video_bytes)
        file_info = finish_res.json()
        file_uri = file_info["file"]["uri"]
        file_name = file_info["file"]["name"]

        # Stap C: Wacht tot Google klaar is met de video
        check_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}"
        while True:
            state_res = requests.get(check_url, headers=headers).json()
            state = state_res.get("state", "PROCESSING")
            if state == "ACTIVE":
                break
            elif state == "FAILED":
                raise Exception("Google video verwerking mislukt.")
            time.sleep(5)

        # 4. Genereer de content via de pure v1beta API
        prompt = (
            f"Je bent een officiële dressuurjury en je jureert strikt volgens de {jury.upper()}-richtlijnen.\n"
            f"Beoordeel de video nauwkeurig op basis van deze proef:\n{proef_tekst}\n\n"
            f"Geef feedback die past bij een {jury} jurering, inclusief scores per onderdeel."
        )

        generate_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        payload = {
            "contents": [{
                "parts": [
                    {"fileData": {"fileUri": file_uri, "mimeType": "video/mp4"}},
                    {"text": prompt}
                ]
            }]
        }

        analysis_res = requests.post(generate_url, json=payload)
        
        # Ruim de video op bij Google
        requests.delete(check_url, headers=headers)
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

        res_json = analysis_res.json()
        text_output = res_json['candidates'][0]['content']['parts'][0]['text']

        return {
            "status": "Succes",
            "jury_stijl": jury,
            "analyse": text_output
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout tijdens de AI-analyse: {str(e)}")
