def get_flash_model_name(headers):
    # Gebruik direct het model dat we in jouw lijst hebben gevonden
    return "models/gemini-3.5-flash"

@app.post("/analyseer")
async def analyseer_video(
    link: str = Query(..., description="Google Drive link naar je video"),
    jury: Literal["mild", "FEI"] = Query(..., description="Kies mild of FEI"),
    proef_pdf: UploadFile = File(..., description="Selecteer je 40.pdf")
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

        # 3. Upload naar Gemini
        headers = {"X-Goog-Api-Key": API_KEY}
        init_res = requests.post("https://generativelanguage.googleapis.com/v1beta/files", 
                                 headers={**headers, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "Content-Type": "application/json"},
                                 json={"file": {"displayName": "video.mp4"}})
        
        upload_url = init_res.headers["X-Goog-Upload-URL"]
        with open(temp_path, "rb") as f:
            final_res = requests.post(upload_url, headers={**headers, "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize", "Content-Type": "video/mp4"}, data=f.read())
        
        file_uri = final_res.json()["file"]["uri"]

        # 4. Analyse met de nieuwe 3.5 Flash
        model_name = get_flash_model_name(headers)
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
        payload = {
            "contents": [{
                "parts": [
                    {"fileData": {"fileUri": file_uri, "mimeType": "video/mp4"}}, 
                    {"text": f"Je bent een dressuurjury. Jury stijl: {jury}. Analyseer de proef op basis van deze richtlijnen: {proef_tekst}"}
                ]
            }]
        }
        
        res = requests.post(url, json=payload).json()
        
        if "candidates" not in res:
            raise Exception(f"Google API gaf een fout: {res}")
            
        return {"analyse": res['candidates'][0]['content']['parts'][0]['text']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fout: {str(e)}")
