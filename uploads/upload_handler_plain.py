"""
This file is for testing file encryption check using LLM.

서버에 파일 업로드 시 암호화를 하지 않는 코드
"""
from flask import Flask, request
import os

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads/plain'

@app.route('/upload_plain', methods=['POST'])
def upload_file_plain():
    file = request.files['file']
    filename = file.filename
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return '파일 업로드 완료'

if __name__ == "__main__":
    app.run(debug=True)