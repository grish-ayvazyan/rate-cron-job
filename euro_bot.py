import os
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime


from telegram.ext import Updater, CommandHandler
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

scheduler = BackgroundScheduler(timezone=pytz.utc)
# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Read Telegram token from environment variable
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Please set TELEGRAM_BOT_TOKEN environment variable")

# Subscribers dictionary:
# chat_id: { threshold: float, from_hour: int, to_hour: int, notified: bool }
subscribers = {}

# Global variables for scheduler job and interval
job = None
check_interval = 5  # default interval in minutes

def get_euro_rate_from_cba():
    url = "https://api.cba.am/exchangerates.asmx"
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://www.cba.am/ExchangeRatesLatest"
    }
    body = """<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                   xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <ExchangeRatesLatest xmlns="http://www.cba.am/" />
      </soap:Body>
    </soap:Envelope>
    """

    response = requests.post(url, data=body, headers=headers)
    if response.status_code == 200:
        xml_root = ET.fromstring(response.text)
        ns = {'ns': 'http://www.cba.am/'}
        rates = xml_root.findall('.//ns:ExchangeRate', ns)
        for rate in rates:
            iso = rate.find('ns:ISO', ns).text
            if iso == 'EUR':
                return float(rate.find('ns:Rate', ns).text)
    logger.warning("Failed to get EUR rate")
    return None

def check_euro_rate(bot):
    eur_value = get_euro_rate_from_cba()
    if eur_value is None:
        logger.error("Failed to fetch euro rate")
        return

    now = datetime.now(pytz.utc).astimezone(pytz.timezone("Asia/Yerevan"))
    current_hour = now.hour

    for chat_id, sub in subscribers.items():
        threshold = sub["threshold"]
        from_hour = sub.get("from_hour", 0)
        to_hour = sub.get("to_hour", 23)
        notified = sub.get("notified", False)

        if from_hour <= current_hour < to_hour:
            if eur_value > threshold and not notified:
                bot.send_message(
                    chat_id=chat_id,
                    text=f"🚨 EUR > {threshold} AMD!\nCurrent: {eur_value:.2f} AMD ({now.strftime('%H:%M')})"
                )
                sub["notified"] = True
            elif eur_value <= threshold and notified:
                # Reset notification flag to allow next alert
                sub["notified"] = False
        else:
            # Outside user defined alert time: reset notified flag
            sub["notified"] = False

def start(update, context):
    update.message.reply_text(
        "Welcome! Use /alert <threshold> [from_hour] [to_hour] to subscribe.\n"
        "Example: /alert 435 9 18\n"
        "Use /unsubscribe to stop alerts.\n"
        "Use /setinterval <minutes> to change check interval (default 5)."
    )

def alert(update, context):
    chat_id = update.message.chat_id
    try:
        threshold = float(context.args[0])
        from_hour = int(context.args[1]) if len(context.args) > 1 else 0
        to_hour = int(context.args[2]) if len(context.args) > 2 else 23

        if not (0 <= from_hour <= 23 and 0 <= to_hour <= 23 and from_hour < to_hour):
            update.message.reply_text("❌ Invalid hours. Use 0-23 and from_hour < to_hour.")
            return

        subscribers[chat_id] = {
            "threshold": threshold,
            "from_hour": from_hour,
            "to_hour": to_hour,
            "notified": False,
        }
        update.message.reply_text(
            f"✅ Subscribed to alerts when EUR > {threshold} AMD between {from_hour}:00–{to_hour}:00."
        )
    except (IndexError, ValueError):
        update.message.reply_text(
            "⚠️ Usage: /alert <threshold> [from_hour] [to_hour]\nExample: /alert 440 9 18"
        )

def unsubscribe(update, context):
    chat_id = update.message.chat_id
    if chat_id in subscribers:
        subscribers.pop(chat_id)
        update.message.reply_text("🛑 You have been unsubscribed from alerts.")
    else:
        update.message.reply_text("ℹ️ You are not subscribed.")

def setinterval(update, context):
    global job, scheduler, check_interval
    try:
        new_interval = int(context.args[0])
        if new_interval < 1:
            update.message.reply_text("❌ Interval must be at least 1 minute.")
            return
    except (IndexError, ValueError):
        update.message.reply_text("⚠️ Usage: /setinterval <minutes>")
        return

    check_interval = new_interval

    if job:
        job.remove()
    job = scheduler.add_job(lambda: check_euro_rate(context.bot), 'interval', minutes=check_interval)
    update.message.reply_text(f"✅ Check interval updated to every {check_interval} minutes.")

def main():
    global scheduler, job, check_interval
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("alert", alert))
    dp.add_handler(CommandHandler("unsubscribe", unsubscribe))
    dp.add_handler(CommandHandler("setinterval", setinterval))

    scheduler.start()
    job = scheduler.add_job(lambda: check_euro_rate(updater.bot), 'interval', minutes=check_interval)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
