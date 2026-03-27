import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN = os.environ.get("API_TOKEN", "YOUR_API_TOKEN")
BASE_URL = f"https://{INSTANCE_ID}.api.greenapi.com/waInstance{INSTANCE_ID}"

GROUP_IDS = {
    "حائل": {
        "هندسية": "120363426950772289@g.us",
        "عقارية": "120363410799982407@g.us",
        "طلابية": "120363407257036510@g.us",
        "عامة":   "120363424571918251@g.us",
        "أخرى":   "120363427416825883@g.us",
    },
    "الرياض": {
        "هندسية": "120363408125014073@g.us",
        "عقارية": "120363409693947081@g.us",
        "طلابية": "",
        "عامة":   "120363424742533865@g.us",
        "أخرى":   "120363424843218984@g.us",
    },
    "مكة": {
        "هندسية": "120363423810536259@g.us",
        "عقارية": "120363408793324975@g.us",
        "طلابية": "",
        "عامة":   "",
        "أخرى":   "120363406558277603@g.us",
    },
}

user_sessions = {}
order_counter = [1000]
pending_orders = {}


def send_message(to, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    chat_id = f"{to}@c.us" if "@" not in to else to
    try:
        requests.post(url, json={"chatId": chat_id, "message": text}, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def send_group_message(group_id, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    try:
        requests.post(url, json={"chatId": group_id, "message": text}, timeout=10)
    except Exception as e:
        print(f"Group error: {e}")


def handle_customer_message(phone, message_text):
    session = user_sessions.get(phone, {"step": "start"})
    step = session.get("step", "start")
    msg = message_text.strip()

    if step == "start":
        send_message(phone,
            "السلام عليكم ورحمة الله\n\n"
            "اهلا بك في شركة ابشر به\n\n"
            "اختر مدينتك:\n"
            "1 - حائل\n"
            "2 - الرياض\n"
            "3 - مكة\n\n"
            "ارسل رقم المدينة"
        )
        user_sessions[phone] = {"step": "choose_city"}

    elif step == "choose_city":
        cities = {"1": "حائل", "2": "الرياض", "3": "مكة"}
        if msg in cities:
            city = cities[msg]
            user_sessions[phone] = {"step": "choose_service", "city": city}
            send_message(phone,
                f"ممتاز! اخترت {city}\n\n"
                "اختر الخدمة المطلوبة:\n"
                "1 - الخدمات الهندسية\n"
                "2 - الخدمات العقارية\n"
                "3 - الخدمات الطلابية\n"
                "4 - الخدمات العامة\n"
                "5 - اخرى\n\n"
                "ارسل رقم الخدمة"
            )
        else:
            send_message(phone, "الرجاء ارسال رقم صحيح (1 او 2 او 3)")

    elif step == "choose_service":
        services = {"1": "هندسية", "2": "عقارية", "3": "طلابية", "4": "عامة", "5": "أخرى"}
        names = {"هندسية": "الهندسية", "عقارية": "العقارية", "طلابية": "الطلابية", "عامة": "العامة", "أخرى": "اخرى"}
        if msg in services:
            sk = services[msg]
            city = session.get("city")
            order_counter[0] += 1
            oid = f"AB-{order_counter[0]}"
            pending_orders[oid] = {"phone": phone, "city": city, "service": sk, "name": names[sk]}
            user_sessions[phone] = {"step": "waiting", "order_id": oid}
            send_message(phone,
                f"تم استلام طلبك بنجاح\n"
                f"رقم الطلب: {oid}\n\n"
                "سيتم ارسال رقم مقدم الخدمة قريبا\n"
                "الرجاء الانتظار"
            )
            gid = GROUP_IDS.get(city, {}).get(sk, "")
            if gid:
                send_group_message(gid,
                    f"طلب جديد\n"
                    f"رقم الطلب: {oid}\n"
                    f"المدينة: {city}\n"
                    f"الخدمة: {names[sk]}\n"
                    f"من يرغب يرد بكلمة: تم"
                )
        else:
            send_message(phone, "الرجاء ارسال رقم من 1 الى 5")

    elif step == "waiting":
        send_message(phone, "طلبك قيد المعالجة، سيتم التواصل معك قريبا")

    elif step == "done":
        user_sessions[phone] = {"step": "start"}
        handle_customer_message(phone, msg)


def handle_group_reply(group_id, sender, sender_name, text):
    if text.strip() == "تم":
        for oid, od in list(pending_orders.items()):
            gid = GROUP_IDS.get(od["city"], {}).get(od["service"], "")
            if gid and gid == group_id:
                cp = od["phone"]
                send_message(cp,
                    f"بشرى سارة!\n\n"
                    f"تم قبول طلبك رقم {oid}\n"
                    f"المدينة: {od['city']}\n"
                    f"الخدمة: {od['name']}\n\n"
                    f"مقدم الخدمة: {sender_name}\n"
                    f"للتواصل: {sender.replace('@c.us','')}\n\n"
                    f"نتمنى لك تجربة ممتازة مع شركة ابشر به"
                )
                del pending_orders[oid]
                if cp in user_sessions:
                    user_sessions[cp]["step"] = "done"
                break


@app.route("/webhook", methods=["POST"])
def receive_message():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "ok"}), 200
        if data.get("typeWebhook") == "incomingMessageReceived":
            sd = data.get("senderData", {})
            md = data.get("messageData", {})
            sender = sd.get("sender", "")
            sender_name = sd.get("senderName", "مقدم الخدمة")
            chat_id = sd.get("chatId", "")
            mt = md.get("typeMessage", "")
            if mt == "textMessage":
                text = md.get("textMessageData", {}).get("textMessage", "")
            elif mt == "extendedTextMessage":
                text = md.get("extendedTextMessageData", {}).get("text", "")
            else:
                text = ""
            if text:
                if "@g.us" in chat_id:
                    handle_group_reply(chat_id, sender, sender_name, text)
                else:
                    handle_customer_message(sender.replace("@c.us", ""), text)
    except Exception as e:
        print(f"Error: {e}")
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "ابشر به - البوت شغال!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
