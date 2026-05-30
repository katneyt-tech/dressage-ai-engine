import os
import time
import requests
import tempfile
import io
import pypdf
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, UploadFile, File

app = FastAPI(title="Dressuur AI API", version="2.1.0")
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

@app.post("/analyseer")
async def analyseer_video(
    link: str = Query(...),
    jury: Literal["mild", "FEI"] = Query(...),
    proef_pdf: UploadFile = File(...)
):
    try:
        # 1. PDF verwerken
        pdf_content = await proef_pdf.read()
        reader = pypdf.PdfReader(io.BytesIO(pdf_content))
        proef_tekst = "".join([page.extract_text() or "" for page in reader.pages])
        
        # 2. Video downloaden
        # Verwijder /view?usp=sharing en voeg de directe download toe
        directe_url = link.replace("/view?usp=sharing", "").replace("file/d/", "uc?export=download&id=")
        video_res = requests.get(directe_url, stream=True)
        if video_res.status_code != 200:
             raise Exception(f"Video download mislukt. HTTP Status: {video_res.status_code}. Controleer de Drive-rechten!")
             
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            for chunk in video_res.iter_content(8192): tmp.write(chunk)
            temp_path = tmp.name

        # 3. Upload naar Gemini
        headers = {"X-Goog-Api-Key": API_KEY}
        
        # Stap A: Init
        init_res = requests.post("https://generativelanguage.googleapis.com/upload/v1beta/files", 
                                 headers={**headers, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "Content-Type": "application/json"},
                                 json={"file": {"displayName": "video.mp4"}})
        
        if init_res.status_code != 200:
            raise Exception(f"Upload init mislukt. Google antwoordde: {init_res.text}")
            
        upload_url = init_res.headers["X-Goog-Upload-URL"]
        
        # Stap B: Upload
        with open(temp_path, "rb") as f:
            final_res = requests.post(upload_url, headers={**headers, "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize", "Content-Type": "video/mp4"}, data=f.read())
        
        if final_res.status_code != 200:
            raise Exception(f"Upload data mislukt. Google antwoordde: {final_res.text}")
        
        file_info = final_res.json()
        file_name = file_info["file"]["name"]

        # 4. Analyse
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        payload = {"contents": [{"parts": [{"fileData": {"fileUri": file_info["file"]["uri"], "mimeType": "video/mp4"}}, {"text": f"Jury {jury}. Proef: {proef_tekst}"}]}]}
        res = requests.post(url, json=payload)
        
        if res.status_code != 200:
            raise Exception(f"Analyse mislukt. Google antwoordde: {res.text}")
        
        res_json = res.json()
        return {"analyse": res_json['candidates'][0]['content']['parts'][0]['text']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout: {str(e)}")
