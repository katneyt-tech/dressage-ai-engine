import os
import time
import requests
import tempfile
import io
import pypdf
import json
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, UploadFile, File

app = FastAPI(title="Dressuur AI Engine", version="3.0.0")
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

# De Revolutionaire Dressuur-Prompt
SYSTEM_PROMPT = """
Je bent een professionele FEI-dressuurjury die jureert op basis van de Klassieke Trainingsschaal (5 lagen): 
1. Fundament (Ritme, Ontspanning, Aanleuning, Impuls, Rechtgerichtheid)
2. Biomechanica (Achterbeen, Schoftlift, Ruggebruik)
3. FEI Proef-structuur
4. Correctie van fouten (Harder straffen voor spanning/conflict dan voor gebrek aan expressie)
5. Contextuele intelligentie (Ras/Niveau)

Geef uitsluitend een JSON-antwoord in dit formaat:
{
  "cijfers": [{"onderdeel": "str", "cijfer": float, "toelichting": "str"}],
  "lagen_score": {"fundament": float, "biomechanica": float, "harmonie": float},
  "algemeen_commentaar": "str",
  "percentage": float,
  "advies": "str"
}
"""

@app.post("/analyseer")
async def analyseer_video(
    link: str = Query(...),
    jury: Literal["mild", "FEI"] = Query(...),
    proef_pdf: UploadFile = File(...)
):
    try:
        # 1. PDF & Video verwerken
        pdf_content = await proef_pdf.read()
        reader = pypdf.PdfReader(io.BytesIO(pdf_content))
        proef_tekst = "".join([page.extract_text() or "" for page in reader.pages])
        
        directe_url = link.replace("/view?usp=sharing", "").replace("file/d/", "uc?export=download&id=")
        video_res = requests.get(directe_url, stream=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            for chunk in video_res.iter_content(8192): tmp.write(chunk)
            temp_path = tmp.name

        # 2. Upload video
        headers = {"X-Goog-Api-Key": API_KEY}
        init_res = requests.post("https://generativelanguage.googleapis.com/upload/v1beta/files", 
                                 headers={**headers, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "Content-Type": "application/json"},
                                 json={"file": {"displayName": "video.mp4"}})
        
        upload_url = init_res.headers["X-Goog-Upload-URL"]
        with open(temp_path, "rb") as f:
            final_res = requests.post(upload_url, headers={**headers, "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize", "Content-Type": "video/mp4"}, data=f.read())
        
        file_info = final_res.json()
        file_name = file_info["file"]["name"]
        
        # 3. Wacht tot Google klaar is
        while True:
            status_res = requests.get(f"https://generativelanguage.googleapis.com/v1beta/{file_name}", headers=headers).json()
            if status_res.get("state") == "ACTIVE": break
            time.sleep(5)

        # 4. Analyse met 3.5-flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={API_KEY}"
        payload = {
            "contents": [{
                "parts": [
                    {"fileData": {"fileUri": file_info["file"]["uri"], "mimeType": "video/mp4"}}, 
                    {"text": f"{SYSTEM_PROMPT}\n\nJury-stijl: {jury}. Analyseer deze proef: {proef_tekst}"}
                ]
            }]
        }
        
        res = requests.post(url, json=payload).json()
        
        # JSON opschonen (soms stuurt Gemini ```json terug)
        raw_text = res['candidates'][0]['content']['parts'][0]['text']
        clean_json = raw_text.replace("```json", "").replace("```", "")
        
        return json.loads(clean_json)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout: {str(e)}")
