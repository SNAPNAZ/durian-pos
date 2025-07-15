from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from datetime import datetime
import qrcode
import io
import os

import gspread
from google.oauth2.service_account import Credentials

# ==== ตั้งค่า Google Sheets ====
SERVICE_ACCOUNT_FILE = 'durian-pos-466019-5234a4d82f4c.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_NAME = 'data'  # ตั้งชื่อ Google Sheets ว่า data

credentials = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
client = gspread.authorize(credentials)
sheet = client.open(SPREADSHEET_NAME).sheet1

# ==== Flask App ====
app = Flask(__name__)
CORS(app)

def get_short_thai_datetime():
    now = datetime.now()
    day = now.day
    month = now.month
    year = (now.year + 543) % 100
    time_str = now.strftime("%H:%M.%S")
    return f"{day:02d}/{month:02d}/{year:02d} {time_str}"

# ===== API หลัก =====
@app.route('/save', methods=['POST'])
def save_data():
    data = request.get_json()
    sheet.append_row([
        get_short_thai_datetime(),
        data["item"],
        float(data["amount"]),
        data["category"],
        data.get("note", "")
    ])
    return "บันทึกสำเร็จ!"

@app.route('/get_data')
def get_data():
    rows = sheet.get_all_values()[1:]  # ข้ามหัว
    return jsonify(rows[-100:])

@app.route('/delete_row', methods=['POST'])
def delete_row():
    data = request.get_json()
    index = data['index'] + 2
    sheet.delete_rows(index)
    return "ลบสำเร็จ"

@app.route('/update_row', methods=['POST'])
def update_row():
    data = request.get_json()
    index = data['index'] + 2
    sheet.update(f"A{index}:E{index}", [[
        data["date"],
        data["item"],
        float(data["amount"]),
        data["category"],
        data.get("note", "")
    ]])
    return "อัปเดตสำเร็จ"

# ===== QR พร้อมเพย์ =====
@app.route('/qr')
def generate_qr():
    national_id = "3100502173223"
    amount = request.args.get("amount", default="0.00")

    qr_data = create_promptpay_payload(national_id, float(amount), is_national_id=True)
    img = qrcode.make(qr_data)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return send_file(buf, mimetype='image/png')

def create_promptpay_payload(target, amount=None, is_national_id=False):
    import re

    def format_target(target, is_national):
        target = re.sub(r"\D", "", target)
        if is_national:
            return target
        if target.startswith("0"):
            return "66" + target[1:]
        return target

    def cal_crc(payload):
        crc = 0xFFFF
        for c in payload.encode("utf-8"):
            crc ^= c << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return format(crc, '04X')

    formatted = format_target(target, is_national_id)
    guid = "A000000677010111"
    acc = f"0213{formatted}" if is_national_id else f"0113{formatted}"
    merchant_info = f"29{len(guid + acc) + 4:02d}0016{guid}{acc}"

    payload = (
        "000201"
        "010211"
        + merchant_info +
        "5303764"
    )

    if amount:
        amt = "{:.2f}".format(amount)
        payload += f"54{len(amt):02d}{amt}"

    payload += "5802TH"
    payload += "6304"
    payload += cal_crc(payload)
    return payload

@app.route('/qr_page')
def qr_page():
    amount = request.args.get("amount", default="0.00")
    return f'''
    <html>
    <head>
        <title>QR พร้อมเพย์</title>
        <style>
            body {{
                font-family: sans-serif;
                text-align: center;
                padding-top: 40px;
            }}
            img {{
                margin: 20px;
                border: 2px solid #333;
                width: 280px;
            }}
            .amount {{
                font-size: 24px;
                margin-top: 10px;
                color: #006600;
            }}
            a {{
                display: inline-block;
                margin-top: 30px;
                text-decoration: none;
                color: white;
                background: #007bff;
                padding: 10px 20px;
                border-radius: 8px;
            }}
        </style>
    </head>
    <body>
        <h2>ชำระเงินผ่านพร้อมเพย์</h2>
        <div class="amount">ยอดเงิน {amount} บาท</div>
        <img src="/qr?amount={amount}" alt="QR พร้อมเพย์">
        <br>
        <a href="/form.html">← กลับไปกรอกข้อมูล</a>
    </body>
    </html>
    '''

# ===== Summary API =====
@app.route('/summary_data')
def summary_data():
    from collections import defaultdict

    rows = sheet.get_all_values()[1:]  # ข้ามหัว

    by_category = defaultdict(float)
    by_item = defaultdict(float)
    total = 0.0

    for row in rows:
        category = row[3]
        item = row[1]
        try:
            amount = float(row[2])
            by_category[category] += amount
            by_item[item] += amount
            total += amount
        except:
            continue

    return jsonify({
        "by_category": dict(by_category),
        "by_item": dict(by_item),
        "total": total
    })

# ===== หน้าเว็บ & Static =====
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# ===== Start =====
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
