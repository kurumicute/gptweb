from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory, send_file, abort
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import openai
import os
import io
from gtts import gTTS
import uuid
from opencc import OpenCC

app = Flask(__name__)
app.secret_key = 'your_secret_key'
openai.api_key = "YOUR_OPENAI_API_KEY"  # 請填入你的 OpenAI API 金鑰

# 設定圖片上傳目錄，若不存在則建立
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
cc = OpenCC('s2twp')  # 簡轉繁（或台灣正體）

# 資料庫配置，請依照你的資料庫設定調整
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'password',
    'database': 'chat_db'
}

# 主頁：返回聊天介面頁面
@app.route('/tts')
def tts():
    # 從 URL 查詢參數取得 text 內容
    text = request.args.get('text', '')
    if not text:
        abort(400, "缺少 'text' 參數")
    try:
        # 使用 gTTS 產生中文語音 (lang 設定為 'zh'，也可以根據需要調整)
        tts = gTTS(text, lang='zh')
        # 將 MP3 輸出到記憶體串流
        audio_io = io.BytesIO()
        tts.write_to_fp(audio_io)
        audio_io.seek(0)
    except Exception as e:
        abort(500, f"TTS 轉換失敗：{e}")
    # 回傳 MP3 檔案內容
    return send_file(audio_io, mimetype='audio/mpeg', as_attachment=False, download_name='tts.mp3')
@app.route('/')
def index():
    return render_template("index.html")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 用户注册
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "需要帳號和密碼！"}), 400
    
    try:
        hashed_password = generate_password_hash(password)
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", 
                      (username, hashed_password))
        conn.commit()
        return jsonify({"success": True})
    except mysql.connector.IntegrityError:
        return jsonify({"error": "帳號已存在！"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# 用户登录
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "需要帳號和密碼！"}), 400

    conn = None
    cursor = None

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({"success": True, "username": user['username']})
        else:
            return jsonify({"error": "帳號或密碼錯誤！"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

@app.route('/get_user')
def get_user():
    if 'username' in session:
        return jsonify({"username": session['username']})
    return jsonify({"username": None})

# 檢查登录狀態
@app.route('/check_session')
def check_session():
    if 'user_id' in session:
        return jsonify({
            "logged_in": True,
            "username": session['username']
        })
    return jsonify({"logged_in": False})

# 用户注销
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return jsonify({"success": True})

# 上傳圖片 API：使用 uuid 產生唯一檔名，避免重複覆蓋
@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({"success": False, "error": "No file part"})
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"})
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        return jsonify({"success": True, "image_url": f"/uploads/{unique_filename}"})
    
    return jsonify({"success": False, "error": "Invalid file type"})

# 返回上傳後的圖片檔案
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 聊天功能：整合圖片與文字，並檢查是否已有相同圖片的回應避免重複分析
@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({"error": "請先登入！"}), 401
    
    user_id = session['user_id']
    user_message = request.json.get("message")
    image_url = request.json.get("image_url")  # 客戶端傳來的圖片 URL
    
    if not user_message and not image_url:
        return jsonify({"error": "消息或圖片不能為空！"}), 400
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # 若有圖片，先檢查是否已有該圖片的回應，避免重複觸發分析
        if image_url:
            cursor.execute(
                "SELECT bot_reply FROM chat WHERE user_id = %s AND image_url = %s ORDER BY id DESC LIMIT 1",
                (user_id, image_url)
            )
            existing = cursor.fetchone()
            if existing:
                return jsonify({"reply": existing['bot_reply']})
        
        # 取得最近的對話歷史（這裡取最新4筆對話）
        cursor.execute(
            "SELECT user_message, bot_reply FROM chat WHERE user_id = %s ORDER BY id DESC LIMIT 4",
            (user_id,)
        )
        history = cursor.fetchall()
        
        messages = []
        for row in reversed(history):
            messages.append({"role": "user", "content": row['user_message']})
            messages.append({"role": "assistant", "content": row['bot_reply']})
        
        if user_message:
            messages.append({"role": "user", "content": user_message})
        
        if image_url:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "請分析這張圖片"},
                    {"type": "image_url", "image_url": {"url": f"https://kurumicute.com{image_url}"}}
                ]
            })
        
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # 使用支持圖片的 GPT-4o 模型
            messages=messages
        )
        reply = response["choices"][0]["message"]["content"]
        traditional_response = cc.convert(reply)
        
        # 儲存對話記錄（同時記錄圖片 URL，若有的話）
        cursor.execute(
            "INSERT INTO chat (user_id, user_message, image_url, bot_reply) VALUES (%s, %s, %s, %s)",
            (user_id, user_message or "圖片上傳", image_url, traditional_response)
        )
        conn.commit()
        
        return jsonify({"reply": traditional_response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# 清除聊天記錄
@app.route('/clear_history', methods=['POST'])
def clear_history():
    if 'user_id' not in session:
        return jsonify({"error": "請先登入！"}), 401

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat WHERE user_id = %s", (session['user_id'],))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# 獲取聊天歷史記錄，包含圖片資訊
@app.route('/history', methods=['GET'])
def history():
    if 'user_id' not in session:
        return jsonify({"error": "請先登入！"}), 401
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_message, image_url, bot_reply FROM chat WHERE user_id = %s ORDER BY id ASC",
            (session['user_id'],)
        )
        chat_history = cursor.fetchall()
        return jsonify(chat_history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=8080)
