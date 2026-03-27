import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# 🔧 إعدادات Green API
# ==========================================
INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN = os.environ.get("API_TOKEN", "YOUR_API_TOKEN")
BASE_URL = f"https://{INSTANCE_ID}.api.greenapi.com/waInstance{INSTANCE_ID}"

# أرقام القروبات — ستضيفها لاحقاً
GROUP_IDS = {
    "هندسية": "",
    "عقارية": "",
    "طلابية": "",
    "عامة": "",
    "أخرى": "",
}

# ==========================================
# حالات المحادثة
# ==========================================
user_sessions = {}
order_counter = [1000]
pending_orders = {}


def send_message(to, text):
    """إرسال رسالة نصية"""
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    data = {
        "chatId": f"{to}@c.us" if "@" not in to else to,
        "message": text
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def send_group_message(group_id, text):
    """إرسال رسالة لقروب"""
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    data = {
        "chatId": group_id,
        "message": text
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Group send error: {e}")


def handle_customer_message(phone, message_text):
    """معالجة رسائل العملاء"""
    session = user_sessions.get(phone, {"step": "start"})
    step = session.get("step", "start")
    msg = message_text.strip()

    if step == "start":
        welcome = (
            "🌟 أهلاً بك في شركة *أبشر به*!\n\n"
            "نسعد بخدمتك، من فضلك اختر مدينتك:\n\n"
            "1️⃣ حائل\n"
            "2️⃣ الرياض\n"
            "3️⃣ مكة\n\n"
            "أرسل رقم المدينة (1 أو 2 أو 3)"
        )
        send_message(phone, welcome)
        user_sessions[phone] = {"step": "choose_city"}

    elif step == "choose_city":
        cities = {"1": "حائل", "2": "الرياض", "3": "مكة"}
        if msg in cities:
            city = cities[msg]
            user_sessions[phone] = {"step": "choose_service", "city": city}
            service_msg = (
                f"📍 ممتاز! اخترت مدينة *{city}*\n\n"
                "ما هي الخدمة المطلوبة؟\n\n"
                "1️⃣ الخدمات الهندسية\n"
                "2️⃣ الخدمات العقارية\n"
                "3️⃣ الخدمات الطلابية\n"
                "4️⃣ الخدمات العامة\n"
                "5️⃣ أخرى\n\n"
                "أرسل رقم الخدمة"
            )
            send_message(phone, service_msg)
        else:
            send_message(phone, "⚠️ الرجاء إرسال رقم صحيح (1 أو 2 أو 3)")

    elif step == "choose_service":
        services = {"1": "هندسية", "2": "عقارية", "3": "طلابية", "4": "عامة", "5": "أخرى"}
        service_names = {
            "هندسية": "الخدمات الهندسية",
            "عقارية": "الخدمات العقارية",
            "طلابية": "الخدمات الطلابية",
            "عامة": "الخدمات العامة",
            "أخرى": "أخرى"
        }
        if msg in services:
            service_key = services[msg]
            city = session.get("city")
            order_counter[0] += 1
            order_id = f"AB-{order_counter[0]}"

            pending_orders[order_id] = {
                "phone": phone,
                "city": city,
                "service": service_key,
                "service_name": service_names[service_key]
            }
            user_sessions[phone] = {"step": "waiting", "order_id": order_id}

            confirm_msg = (
                f"✅ عزيزي العميل\n\n"
                f"تم استلام طلبك بنجاح!\n"
                f"رقم طلبك: *{order_id}*\n\n"
                f"سوف نقوم بإرسال رقم مقدم الخدمة لك قريباً.\n"
                f"الرجاء الانتظار 🙏"
            )
            send_message(phone, confirm_msg)

            group_id = GROUP_IDS.get(service_key, "")
            if group_id:
                group_msg = (
                    f"🔔 *طلب جديد*\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"📋 رقم الطلب: *{order_id}*\n"
                    f"📍 المدينة: *{city}*\n"
                    f"🔧 الخدمة: *{service_names[service_key]}*\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"من يرغب بتنفيذ الطلب يرد بـ *تم*"
                )
                send_group_message(group_id, group_msg)
        else:
            send_message(phone, "⚠️ الرجاء إرسال رقم صحيح من 1 إلى 5")

    elif step == "waiting":
        send_message(phone, "⏳ طلبك قيد المعالجة، سيتم التواصل معك قريباً. شكراً لصبرك 🙏")


def handle_group_reply(group_id, sender_phone, sender_name, message_text):
    """معالجة ردود أعضاء القروب"""
    if message_text.strip() == "تم":
        for order_id, order_data in list(pending_orders.items()):
            service_key = order_data.get("service")
            expected_group = GROUP_IDS.get(service_key, "")
            if expected_group and expected_group == group_id:
                customer_phone = order_data["phone"]
                city = order_data["city"]
                service_name = order_data["service_name"]

                notify_msg = (
                    f"🎉 بشرى سارة!\n\n"
                    f"تم قبول طلبك رقم *{order_id}*\n"
                    f"📍 المدينة: {city}\n"
                    f"🔧 الخدمة: {service_name}\n\n"
                    f"مقدم الخدمة: *{sender_name}*\n"
                    f"📞 للتواصل: {sender_phone}\n\n"
                    f"نتمنى لك تجربة ممتازة مع شركة أبشر به 🌟"
                )
                send_message(customer_phone, notify_msg)
                del pending_orders[order_id]
                if customer_phone in user_sessions:
                    user_sessions[customer_phone]["step"] = "done"
                break


# ==========================================
# Webhook — استقبال الرسائل من Green API
# ==========================================

@app.route("/webhook", methods=["POST"])
def receive_message():
    """استقبال الرسائل"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "ok"}), 200

        type_webhook = data.get("typeWebhook", "")

        if type_webhook == "incomingMessageReceived":
            sender_data = data.get("senderData", {})
            message_data = data.get("messageData", {})

            sender = sender_data.get("sender", "")
            sender_name = sender_data.get("senderName", "مقدم الخدمة")
            chat_id = sender_data.get("chatId", "")

            msg_type = message_data.get("typeMessage", "")
            if msg_type == "textMessage":
                text = message_data.get("textMessageData", {}).get("textMessage", "")
            elif msg_type == "extendedTextMessage":
                text = message_data.get("extendedTextMessageData", {}).get("text", "")
            else:
                text = ""

            if not text:
                return jsonify({"status": "ok"}), 200

            # تحديد إذا من قروب أو عميل
            if "@g.us" in chat_id:
                handle_group_reply(chat_id, sender.replace("@c.us", ""), sender_name, text)
            else:
                phone = sender.replace("@c.us", "")
                handle_customer_message(phone, text)

    except Exception as e:
        print(f"Webhook error: {e}")

    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "أبشر به - البوت شغّال! ✅", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
