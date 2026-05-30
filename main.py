import os
import time
import requests
import tempfile
import io
import pypdf
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, UploadFile, File

app = FastAPI(title="Dressuur AI API", version="2.0.0")
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
        directe_url = link.replace("/view?usp=sharing", "").replace("file/d/", "uc?export=download&id=")
        video_res = requests.get(directe_url, stream=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            for chunk in video_res.iter_content(8192): tmp.write(chunk)
            temp_path = tmp.name

        # 3. Upload naar Gemini via REST (nieuwe methode)
        headers = {"X-Goog-Api-Key": API_KEY}
        
        # Stap A: Init
        init_res = requests.post("https://generativelanguage.googleapis.com/upload/v1beta/files", 
                                 headers={**headers, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "Content-Type": "application/json"},
                                 json={"file": {"displayName": "video.mp4"}})
        upload_url = init_res.headers["X-Goog-Upload-URL"]
        
        # Stap B: Upload
        with open(temp_path, "rb") as f:
            requests.post(upload_url, headers={**headers, "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize", "Content-Type": "video/mp4"}, data=f.read())
        
        # Wacht op verwerking
        file_name = init_res.json()["file"]["name"]
        while True:
            state = requests.get(f"https://generativelanguage.googleapis.com/v1beta/{file_name}", headers=headers).json()
            if state.get("state") == "ACTIVE": break
            if state.get("state") == "FAILED": raise Exception(f"Video verwerking gefaald: {state}")
            time.sleep(2)

        # 4. Analyse
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        payload = {"contents": [{"parts": [{"fileData": {"fileUri": state["uri"], "mimeType": "video/mp4"}}, {"text": f"Jury {jury}. Proef: {proef_tekst}"}]}]}
        res = requests.post(url, json=payload).json()
        
        # CRUCIALE FOUTAFVANGST
        if "candidates" not in res:
            raise Exception(f"Google API gaf geen resultaat terug. Respons: {res}")
            
        return {"analyse": res['candidates'][0]['content']['parts'][0]['text']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout: {str(e)}")
