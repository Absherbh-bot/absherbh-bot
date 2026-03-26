import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# 🔧 إعدادات — غيّر هذه القيم فقط
# ==========================================
VERIFY_TOKEN = "abshir_secret_2024"          # رمز سري تختاره أنت
ACCESS_TOKEN = "YOUR_META_ACCESS_TOKEN"       # من لوحة Meta Developers
PHONE_NUMBER_ID = "YOUR_PHONE_NUMBER_ID"      # من لوحة Meta Developers

# أرقام المجموعات (Group IDs) — تحتاج تعبئها بعد ربط البوت
GROUP_IDS = {
    "هندسية": "GROUP_ID_ENGINEERING",
    "عقارية": "GROUP_ID_REAL_ESTATE",
    "طلابية": "GROUP_ID_STUDENTS",
    "عامة":   "GROUP_ID_GENERAL",
    "أخرى":   "GROUP_ID_OTHER",
}

# ==========================================
# حالات المحادثة لكل مستخدم
# ==========================================
user_sessions = {}  # { phone: { step, city, service, order_id } }
order_counter = [1000]  # عداد أرقام الطلبات
pending_orders = {}     # { "order_id": { phone, city, service } }


def send_message(to, text):
    """إرسال رسالة نصية للعميل"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, headers=headers, json=data)


def send_group_message(group_id, text):
    """إرسال رسالة لقروب معين"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": group_id,
        "type": "text",
        "text": {"body": text}
    }
    requests.post(url, headers=headers, json=data)


def handle_customer_message(phone, message_text):
    """معالجة رسائل العملاء خطوة بخطوة"""
    session = user_sessions.get(phone, {"step": "start"})
    step = session.get("step", "start")
    msg = message_text.strip()

    # ========== الخطوة 1: ترحيب واختيار المدينة ==========
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

    # ========== الخطوة 2: اختيار المدينة ==========
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

    # ========== الخطوة 3: اختيار الخدمة ==========
    elif step == "choose_service":
        services = {
            "1": "هندسية",
            "2": "عقارية",
            "3": "طلابية",
            "4": "عامة",
            "5": "أخرى"
        }
        service_names = {
            "هندسية": "الخدمات الهندسية",
            "عقارية": "الخدمات العقارية",
            "طلابية": "الخدمات الطلابية",
            "عامة":   "الخدمات العامة",
            "أخرى":   "أخرى"
        }
        if msg in services:
            service_key = services[msg]
            city = session.get("city")

            # توليد رقم طلب
            order_counter[0] += 1
            order_id = f"AB-{order_counter[0]}"

            # حفظ الطلب
            pending_orders[order_id] = {
                "phone": phone,
                "city": city,
                "service": service_key,
                "service_name": service_names[service_key]
            }
            user_sessions[phone] = {"step": "waiting", "order_id": order_id}

            # إشعار العميل
            confirm_msg = (
                f"✅ عزيزي العميل\n\n"
                f"تم استلام طلبك بنجاح!\n"
                f"رقم طلبك: *{order_id}*\n\n"
                f"سوف نقوم بإرسال رقم مقدم الخدمة لك قريباً.\n"
                f"الرجاء الانتظار 🙏"
            )
            send_message(phone, confirm_msg)

            # إرسال الطلب للقروب المختص
            group_id = GROUP_IDS.get(service_key)
            if group_id and not group_id.startswith("GROUP_ID"):
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

    # ========== في حالة الانتظار ==========
    elif step == "waiting":
        send_message(phone, "⏳ طلبك قيد المعالجة، سيتم التواصل معك قريباً. شكراً لصبرك 🙏")


def handle_group_reply(group_id, sender_phone, sender_name, message_text):
    """معالجة ردود أعضاء القروب"""
    msg = message_text.strip().lower()

    if msg == "تم":
        # البحث عن طلب معلق في هذا القروب
        for order_id, order_data in list(pending_orders.items()):
            service_key = order_data.get("service")
            expected_group = GROUP_IDS.get(service_key)

            if expected_group == group_id:
                customer_phone = order_data["phone"]
                city = order_data["city"]
                service_name = order_data["service_name"]

                # إشعار العميل ببيانات مقدم الخدمة
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

                # حذف الطلب من القائمة المعلقة
                del pending_orders[order_id]

                # تحديث حالة العميل
                if customer_phone in user_sessions:
                    user_sessions[customer_phone]["step"] = "done"
                break


# ==========================================
# Webhook — نقطة الاتصال مع Meta
# ==========================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """التحقق من الـ Webhook عند الإعداد"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    """استقبال الرسائل من واتس آب"""
    data = request.get_json()

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        messages = value.get("messages", [])
        contacts = value.get("contacts", [])

        for message in messages:
            sender_phone = message["from"]
            msg_type = message.get("type")

            if msg_type == "text":
                msg_text = message["text"]["body"]

                # تحديد ما إذا كان المرسل من قروب أو عميل فردي
                # القروبات تبدأ بـ @g.us في الـ group_id
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")

                # إذا كانت الرسالة من قروب
                if "g.us" in sender_phone:
                    sender_name = contacts[0]["profile"]["name"] if contacts else "مقدم الخدمة"
                    handle_group_reply(sender_phone, sender_phone, sender_name, msg_text)
                else:
                    # رسالة من عميل
                    handle_customer_message(sender_phone, msg_text)

    except Exception as e:
        print(f"Error: {e}")

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
