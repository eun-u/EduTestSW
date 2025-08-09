"""
This file is for testing file encryption check using LLM.

서버에 파일 업로드 시 암호화 저장하는 코드
"""
from flask import Flask, request
import os
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads/encrypted'
KEY = b'ThisIsA16ByteKey_'  # AES256을 위해 32바이트 키를 써도 됨 (예시)

def pad(data):
    length = 16 - len(data) % 16
    return data + bytes([length]) * length

@app.route('/upload_encrypted', methods=['POST'])
def upload_file_encrypted():
    file = request.files['file']
    data = file.read()

    cipher = AES.new(KEY, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(data))
    iv = cipher.iv
    encrypted_data = iv + ct_bytes  # CBC는 IV를 함께 저장해야 복호화 가능

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    with open(os.path.join(UPLOAD_FOLDER, file.filename + ".enc"), "wb") as f:
        f.write(encrypted_data)

    return '파일 업로드 완료'

if __name__ == "__main__":
    app.run(debug=True)