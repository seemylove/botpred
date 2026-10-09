import os
import threading
from flask import Flask
from bot import dp, bot  # твой бот.py

app = Flask(__name__)

@app.route("/")
@app.route("/health")
def health():
    return "OK"

def run_bot():
    import asyncio
    asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
