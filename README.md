# ChatGPT web

這是一個仿 ChatGPT 的網站專案，使用 Flask 作為後端、MySQL 作為資料庫，並整合 OpenAI API、TTS、圖片上傳及簡繁轉換等功能。

## 功能

- 使用者註冊與登入
- 聊天功能（文字及圖片）
- TTS 語音輸出
- 聊天記錄儲存與清除
- 簡體轉繁體（台灣正體）轉換

## 安裝步驟

1. **Clone repository**

   ```bash
   https://github.com/kurumicute/gptweb.git
   cd chatgpt-clone
2.建立虛擬環境並安裝依賴

```
   python -m venv venv
   source venv/bin/activate   # Windows 請使用 venv\Scripts\activate
   pip install -r requirements.txt
```
3.設定資料庫

請建立一個名為 chat_db 的 MySQL 資料庫。
建立 users 與 chat 表，範例如下：
```
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL
);

CREATE TABLE chat (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    user_message TEXT,
    image_url VARCHAR(255),
    bot_reply TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```
4.設定 API 金鑰與其他參數

修改 app.py 中的 OpenAI API 金鑰設定（建議使用環境變數）。
修改資料庫連線參數 DB_CONFIG。

5.啟動伺服器
python app.py

6.前往 http://localhost:8080 即可使用此應用程式。
