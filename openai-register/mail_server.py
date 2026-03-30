import json
import re
import os
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# 配置
PORT = 18001
SAVE_DIR = "received_emails"  # 邮件原始内容保存目录
STORAGE_FILE = "emails_db.json" # 验证码映射文件

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# 内存缓存，加速查询
otp_cache = {}

def save_to_local(data):
    """将原始邮件 JSON 保存到本地文件系统"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(SAVE_DIR, f"mail_{timestamp}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    if not data:
        return "No Data", 200

    # 1. 持久化保存原始数据
    save_to_local(data)

    # 2. 提取核心信息
    inner = data.get('data', {})
    to_emails = inner.get('to', [])
    subject = inner.get('subject', "")
    content = inner.get('text') or inner.get('html') or ""

    # 3. 提取验证码并存入缓存
    if to_emails:
        target_email = to_emails[0].lower()
        # 扫描标题和正文中的 6 位数字
        match = re.search(r"\b(\d{6})\b", f"{subject} | {content}")
        if match:
            code = match.group(1)
            otp_cache[target_email] = code
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 收到邮件: {target_email} -> Code: {code}")

    return "OK", 200

@app.route('/get_otp', methods=['GET'])
def get_otp():
    """供注册脚本调用的 API"""
    email = request.args.get('email', '').lower()
    code = otp_cache.get(email)
    if code:
        # 取走后可以选择是否删除（阅后即焚）
        # del otp_cache[email]
        return jsonify({"status": "success", "code": code})
    return jsonify({"status": "pending", "code": None})

if __name__ == '__main__':
    print(f"邮件接收服务启动... 监听端口: {PORT}")
    app.run(host='0.0.0.0', port=PORT)
