import os
import time
import requests
import tempfile
import io
import pypdf
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, UploadFile, File

app = FastAPI(title="Dressuur AI API", version="2.4.0")
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")

def get_flash_model_name():
    return "models/gemini-3.5-flash"

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
        
        # 3. Wacht tot Google de video heeft verwerkt (CRUCIAAL)
        while True:
            status_res = requests.get(f"https://generativelanguage.googleapis.com/v1beta/{file_name}", headers=headers).json()
            state = status_res.get("state")
            if state == "ACTIVE":
                break
            elif state == "FAILED":
                raise Exception("Google kon de video niet verwerken.")
            time.sleep(5) # Wacht 5 seconden en probeer opnieuw

        # 4. Analyseer
        model_name = get_flash_model_name()
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
        payload = {"contents": [{"parts": [{"fileData": {"fileUri": file_info["file"]["uri"], "mimeType": "video/mp4"}}, {"text": f"Jury {jury}. Proef: {proef_tekst}"}]}]}
        res = requests.post(url, json=payload).json()
        
        return {"analyse": res['candidates'][0]['content']['parts'][0]['text']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout: {str(e)}")
