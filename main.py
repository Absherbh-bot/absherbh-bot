import os
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN = os.environ.get("API_TOKEN", "YOUR_API_TOKEN")
BASE_URL = f"https://7107.api.greenapi.com/waInstance{INSTANCE_ID}"

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
        "طلابية": "120363409659806706@g.us",
        "عامة":   "120363424742533865@g.us",
        "أخرى":   "120363424843218984@g.us",
    },
    "مكة": {
        "هندسية": "120363423810536259@g.us",
        "عقارية": "120363408793324975@g.us",
        "طلابية": "120363424890108033@g.us",
        "عامة":   "120363427195136751@g.us",
        "أخرى":   "120363406558277603@g.us",
    },
}

user_sessions = {}
order_counter = [1000]
pending_orders = {}
# { phone: { until: timestamp } }
blocked_users = {}


def is_blocked(phone):
    if phone in blocked_users:
        until = blocked_users[phone]["until"]
        remaining = int((until - time.time()) / 60)
        if time.time() < until:
            return True, remaining
        else:
            del blocked_users[phone]
    return False, 0


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
    # التحقق من الحظر المؤقت
    blocked, remaining = is_blocked(phone)
    if blocked:
        send_message(phone,
            f"عزيزي العميل\n"
            f"حسابك موقوف مؤقتاً\n"
            f"المتبقي: {remaining} دقيقة\n"
            f"يرجى المحاولة لاحقاً"
        )
        return

    session = user_sessions.get(phone, {"step": "start"})
    step = session.get("step", "start")
    msg = message_text.strip()

    # الخطوة 1: ترحيب
    if step == "start":
        send_message(phone,
            ""
            "اهلا بك في ابشر به\n\n"
            "اختر مدينتك:\n"
            "1 - حائل\n"
            "2 - الرياض\n"
            "3 - مكة\n\n"
            "ارسل رقم المدينة"
        )
        user_sessions[phone] = {"step": "choose_city"}

    # الخطوة 2: اختيار المدينة
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

    # الخطوة 3: اختيار الخدمة
    elif step == "choose_service":
        services = {"1": "هندسية", "2": "عقارية", "3": "طلابية", "4": "عامة", "5": "أخرى"}
        names = {"هندسية": "الهندسية", "عقارية": "العقارية", "طلابية": "الطلابية", "عامة": "العامة", "أخرى": "اخرى"}
        if msg in services:
            sk = services[msg]
            city = session.get("city")
            order_counter[0] += 1
            oid = f"AB-{order_counter[0]}"
            pending_orders[oid] = {
                "phone": phone,
                "city": city,
                "service": sk,
                "name": names[sk],
                "attempts": 1,
                "blocked_providers": [],
                "last_price": None
            }
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
                    f"━━━━━━━━━━━━━━\n"
                    f"لاستلام الطلب تفاعل مع الرسالة\n"
                    f"اضغط مطولاً على الرسالة واختر أي تفاعل\n\n"
                    f"To accept, react to this message\n"
                    f"Press and hold the message, then select any reaction\n\n"
                    f"آرڈر لینے کے لیے میسج پر ری ایکشن دیں\n"
                    f"میسج کو دیر تک دبائیں اور کوئی بھی ری ایکشن منتخب کریں\n"
                    f"━━━━━━━━━━━━━━"
                )
        else:
            send_message(phone, "الرجاء ارسال رقم من 1 الى 5")

    # الخطوة 4: انتظار بعد إرسال مقدم الخدمة
    elif step == "provider_sent":
        oid = session.get("order_id")
        if msg == "1":
            # ممتاز - تم الاتفاق
            send_message(phone, "ممتاز! نتمنى لك تجربة رائعة مع ابشر به")
            if oid in pending_orders:
                del pending_orders[oid]
            user_sessions[phone] = {"step": "start"}

        elif msg == "2":
            # إعادة الطلب
            if oid in pending_orders:
                attempts = pending_orders[oid].get("attempts", 1)
                if attempts >= 3:
                    # إيقاف 15 دقيقة
                    blocked_users[phone] = {"until": time.time() + 15 * 60}
                    send_message(phone,
                        "عزيزي العميل\n"
                        "تم استنفاد المحاولات الثلاث\n"
                        "سيتم إيقاف طلباتك لمدة 15 دقيقة\n"
                        "يمكنك المحاولة مجدداً بعد قليل"
                    )
                    del pending_orders[oid]
                    user_sessions[phone] = {"step": "start"}
                else:
                    user_sessions[phone] = {"step": "reason_return", "order_id": oid}
                    send_message(phone,
                        "ما سبب عدم الاتفاق؟\n\n"
                        "1 - السعر مرتفع\n"
                        "2 - لم يتجاوب مقدم الخدمة\n"
                        "3 - سبب آخر"
                    )
            else:
                user_sessions[phone] = {"step": "start"}

        elif msg == "3":
            # تواصل مع الإدارة
            send_message(phone,
                "سيتم تحويلك للإدارة\n"
                "للتواصل المباشر: 0554325282"
            )
            user_sessions[phone] = {"step": "start"}

        else:
            send_message(phone,
                "كيف كانت تجربتك مع مقدم الخدمة؟\n\n"
                "1 - ممتاز تم الاتفاق\n"
                "2 - لم يتم الاتفاق (إعادة الطلب)\n"
                "3 - تواصل مع الإدارة"
            )

    # الخطوة 5: سبب الإعادة
    elif step == "reason_return":
        oid = session.get("order_id")
        if msg == "1":
            # السعر مرتفع
            user_sessions[phone] = {"step": "enter_price", "order_id": oid}
            send_message(phone, "كم السعر الذي عُرض عليك؟ (اكتب المبلغ بالريال)")

        elif msg == "2":
            # لم يتجاوب
            if oid in pending_orders:
                _resend_order(phone, oid, "لم يتجاوب مقدم الخدمة", None)
        elif msg == "3":
            # سبب آخر
            user_sessions[phone] = {"step": "enter_reason", "order_id": oid}
            send_message(phone, "اكتب سبب عدم الاتفاق")
        else:
            send_message(phone,
                "الرجاء اختيار رقم صحيح:\n"
                "1 - السعر مرتفع\n"
                "2 - لم يتجاوب مقدم الخدمة\n"
                "3 - سبب آخر"
            )

    # الخطوة 6: إدخال السعر
    elif step == "enter_price":
        oid = session.get("order_id")
        _resend_order(phone, oid, "السعر مرتفع", msg)

    # الخطوة 7: إدخال السبب
    elif step == "enter_reason":
        oid = session.get("order_id")
        _resend_order(phone, oid, msg, None)

    elif step == "waiting":
        send_message(phone, "طلبك قيد المعالجة، سيتم التواصل معك قريبا")


def _resend_order(phone, oid, reason, price):
    if oid not in pending_orders:
        return
    od = pending_orders[oid]
    od["attempts"] += 1
    attempts = od["attempts"]
    city = od["city"]
    sk = od["service"]
    if price:
        od["last_price"] = price

    gid = GROUP_IDS.get(city, {}).get(sk, "")
    if gid:
        price_line = f"آخر سعر مُقدَّم: {od['last_price']} ريال\n" if od.get("last_price") else ""
        send_group_message(gid,
            f"طلب معاد - المحاولة {attempts} من 3\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {city}\n"
            f"الخدمة: {od['name']}\n"
            f"{price_line}"
            f"سبب الإعادة: {reason}\n"
            f"من يرغب يرد بـ: 1\n"
            f"مقدمو الخدمة السابقون لا يحق لهم المشاركة"
        )

    attempt_warning = ""
    if attempts == 3:
        attempt_warning = "\nتنبيه: هذه آخر محاولة متاحة لك"

    send_message(phone,
        f"تم إعادة طلبك\n"
        f"المحاولة {attempts} من 3\n"
        f"سيتم التواصل معك قريبا{attempt_warning}"
    )
    user_sessions[phone] = {"step": "waiting", "order_id": oid}


def handle_group_reply(group_id, sender, sender_name, reaction=None):
    for oid, od in list(pending_orders.items()):
        gid = GROUP_IDS.get(od["city"], {}).get(od["service"], "")
        if gid and gid == group_id:
            sender_clean = sender.replace("@c.us", "")

            # التحقق أن مقدم الخدمة ليس محظوراً
            if sender_clean in od.get("blocked_providers", []):
                return

            # التحقق أن الطلب لم يُؤخذ بعد
            if od.get("taken"):
                return

            cp = od["phone"]
            od["blocked_providers"].append(sender_clean)
            od["taken"] = True

            send_message(cp,
                f"ابشر به\n\n"
                f"تم قبول طلبك رقم {oid}\n"
                f"المدينة: {od['city']}\n"
                f"الخدمة: {od['name']}\n\n"
                f"مقدم الخدمة: {sender_name}\n"
                f"للتواصل: {sender_clean}"
            )
            send_message(cp,
                "كيف كانت تجربتك مع مقدم الخدمة؟\n\n"
                "1 - ممتاز تم الاتفاق\n"
                "2 - لم يتم الاتفاق (إعادة الطلب)\n"
                "3 - تواصل مع الإدارة"
            )
            user_sessions[cp] = {"step": "provider_sent", "order_id": oid}
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

            # التفاعلات (reactions) من القروب
            if mt == "reactionMessage":
                if "@g.us" in chat_id:
                    handle_group_reply(chat_id, sender, sender_name, reaction=True)
                return jsonify({"status": "ok"}), 200

            if mt == "textMessage":
                text = md.get("textMessageData", {}).get("textMessage", "")
            elif mt == "extendedTextMessage":
                text = md.get("extendedTextMessageData", {}).get("text", "")
            else:
                text = ""
            if text:
                if "@g.us" in chat_id:
                    pass  # القروب مقفول للرسائل النصية
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
