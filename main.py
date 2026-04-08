import os
import time
import json
import requests
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import io

app = Flask(__name__)

# ==========================================
# تحويل الأرقام العربية للإنجليزية
# ==========================================
def normalize(text):
    """تحويل الأرقام العربية فقط — لا يمس النصوص"""
    arabic = '٠١٢٣٤٥٦٧٨٩'
    for i, a in enumerate(arabic):
        text = text.replace(a, str(i))
    return text.strip()

# ==========================================
# إعدادات Green API
# ==========================================
# ==========================================
# الحساب الرئيسي
# ==========================================
INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107579979")
API_TOKEN   = os.environ.get("API_TOKEN", "5c1dd144d2ff4079b484b1362e763bc18dc5ebfc12e049acbe")
BASE_URL    = f"https://7107.api.greenapi.com/waInstance{INSTANCE_ID}"
BANK_ACCOUNT   = "SA2880000595608016106214"
EXPORT_SECRET  = os.environ.get("EXPORT_SECRET", "ms-export-2026")
ADMIN_GROUP   = "120363406971255280@g.us"
SUBSCRIBERS_GROUP = "120363406971255280@g.us"
CONTROL_GROUP = "120363425363360676@g.us"

# أرقام مصرح لها بالتحكم
ADMIN_PHONES = {"966531157747"}  # رقم المتحكم الثابت

# ==========================================
# اللغات
# ==========================================
LANGUAGES = {
    "1": {"code": "ar", "name": "العربية"},
    "2": {"code": "en", "name": "English"},
    "3": {"code": "ur", "name": "اردو"},
}

# ==========================================
# المدن
# ==========================================
CITIES = {
    "1":  "حائل",
    "2":  "الرياض",
    "3":  "جدة",
    "4":  "مكة المكرمة",
    "5":  "المدينة المنورة",
    "6":  "الدمام",
    "7":  "الخبر",
    "8":  "الأحساء",
    "9":  "تبوك",
    "10": "أبها",
    "11": "القصيم",
    "12": "خميس مشيط",
    "13": "الطائف",
    "14": "ينبع",
    "15": "الجبيل",
    "16": "القطيف",
    "17": "نجران",
    "18": "جازان",
    "19": "سكاكا",
    "20": "حفر الباطن",
    "21": "عرعر",
    "22": "الجوف",
    "23": "رفحاء",
    "24": "الباحة",
    "25": "عسير",
}

# ==========================================
# الخدمات
# ==========================================
SERVICES = {
    "1": "الخدمات الهندسية",
    "2": "الخدمات العقارية",
    "3": "الخدمات الطلابية",
    "4": "مناديب التوصيل",
    "5": "شاليهات",
    "6": "صهريج مياه",
    "7": "اسطوانات الغاز",
    "8": "سطحات",
}

# ==========================================
# Render Disk
# ==========================================
DATA_PATH      = "/opt/render/project/data"
PROVIDERS_FILE = f"{DATA_PATH}/providers.json"
CLIENTS_FILE   = f"{DATA_PATH}/clients.json"
ORDERS_FILE    = f"{DATA_PATH}/orders.json"
COUNTER_FILE   = f"{DATA_PATH}/counter.json"
LOG_FILE       = f"{DATA_PATH}/activity_log.json"

# ==========================================
# البيانات في الذاكرة
# ==========================================
user_sessions     = {}
activity_log      = []  # سجل العمليات
provider_sessions = {}
control_sessions  = {}
registered_clients   = set()
registered_providers = {}
pending_orders    = {}
blocked_users     = {}
order_counter     = [1000]
last_activity     = {}
registration_requests = {}
registration_cooldown = {}
SESSION_TIMEOUT   = 2 * 60  # دقيقتان
REGISTRATION_COOLDOWN = 24 * 60 * 60
REGISTRATION_TIMEOUT = 5 * 60

# ==========================================
# حفظ وتحميل البيانات
# ==========================================
def load_data():
    global registered_providers, registered_clients, pending_orders, order_counter
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        if os.path.exists(PROVIDERS_FILE):
            with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
                registered_providers = json.load(f)
            print(f"✅ تم تحميل {len(registered_providers)} مقدم خدمة")
        if os.path.exists(CLIENTS_FILE):
            with open(CLIENTS_FILE, "r", encoding="utf-8") as f:
                registered_clients = set(json.load(f))
            print(f"✅ تم تحميل {len(registered_clients)} عميل")
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                order_counter[0] = json.load(f).get("counter", 1000)
            print(f"✅ تم تحميل العداد: {order_counter[0]}")
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                activity_log.extend(json.load(f))
            print(f"✅ تم تحميل {len(activity_log)} سجل")
        if os.path.exists(ORDERS_FILE):
            with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for oid, od in saved.items():
                if not od.get("taken") and od.get("providers"):
                    pending_orders[oid] = od
                    # إعادة تشغيل الطلبات المعلقة
                    od["taken"] = False
                    threading.Timer(2, broadcast_order, args=[oid]).start()
            print(f"✅ تم تحميل {len(pending_orders)} طلب معلق")
    except Exception as e:
        print(f"خطأ تحميل: {e}")

def save_providers():
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(registered_providers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ حفظ مقدمين: {e}")

def save_clients():
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(registered_clients), f, ensure_ascii=False)
    except Exception as e:
        print(f"خطأ حفظ عملاء: {e}")

def save_counter():
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(COUNTER_FILE, "w", encoding="utf-8") as f:
            json.dump({"counter": order_counter[0]}, f)
    except Exception as e:
        print(f"خطأ حفظ عداد: {e}")

def save_orders():
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(pending_orders, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ حفظ طلبات: {e}")

def log_event(event_type, phone, details="", order_id=""):
    """تسجيل كل حدث فوري"""
    entry = {
        "time":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type":       event_type,
        "phone":      phone,
        "order_id":   order_id,
        "details":    details,
    }
    activity_log.append(entry)
    # حفظ فوري
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(activity_log[-5000:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ حفظ سجل: {e}")

# ==========================================
# دوال الإرسال
# ==========================================
def send_msg(to, text):
    url     = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    chat_id = f"{to}@c.us" if "@" not in to else to
    try:
        r = requests.post(url, json={"chatId": chat_id, "message": text}, timeout=10)
        return r.json().get("idMessage", "")
    except Exception as e:
        print(f"Send error: {e}")
        return ""

def send_group(gid, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    try:
        r = requests.post(url, json={"chatId": gid, "message": text}, timeout=10)
        return r.json().get("idMessage", "")
    except Exception as e:
        print(f"Group error: {e}")
        return ""

# ==========================================
# دوال مساعدة
# ==========================================
def count_providers(city, service):
    return sum(
        1 for d in registered_providers.values()
        if d.get("city") == city
        and d.get("specialty") == service
        and d.get("status") == "active"
    )

def check_subscription(provider):
    expiry = provider.get("expiry", "")
    if not expiry:
        return True
    try:
        return datetime.now() < datetime.strptime(expiry, "%Y-%m-%d")
    except:
        return True

def is_blocked(phone):
    if phone in blocked_users:
        until = blocked_users[phone]
        if time.time() < until:
            return True, int((until - time.time()) / 60)
        del blocked_users[phone]
    return False, 0

def check_timeout(phone):
    """دقيقتان بدون نشاط = إعادة البدء"""
    now = time.time()
    if phone in last_activity:
        if now - last_activity[phone] > SESSION_TIMEOUT:
            user_sessions.pop(phone, None)
            provider_sessions.pop(phone, None)
            last_activity[phone] = now
            return True
    last_activity[phone] = now
    return False


def registration_cooldown_remaining(phone):
    last_try = registration_cooldown.get(phone, 0)
    remaining = REGISTRATION_COOLDOWN - (time.time() - last_try)
    return max(0, int(remaining))


def format_remaining_hours(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours} ساعة و{minutes} دقيقة"


def can_start_registration(phone):
    return registration_cooldown_remaining(phone) == 0


def send_provider_specialty_menu(phone):
    send_msg(phone,
        "اختر تخصصك:\n\n"
        "1 - الخدمات الهندسية\n"
        "2 - الخدمات العقارية\n"
        "3 - الخدمات الطلابية\n"
        "4 - مناديب التوصيل\n"
        "5 - شاليهات\n"
        "6 - صهريج مياه\n"
        "7 - اسطوانات الغاز\n"
        "8 - سطحات\n\n"
        "ارسل رقم تخصصك\n"
        "0  - رجوع ↩️"
    )


def get_oldest_pending_registration():
    pending = [r for r in registration_requests.values() if not r.get("approved") and time.time() < r.get("expires_at", 0)]
    if not pending:
        return None
    pending.sort(key=lambda item: item.get("created_at", 0))
    return pending[0]


def send_registration_request(phone, provider_data):
    registration_cooldown[phone] = time.time()

    req_id = f"REG-{int(time.time())}-{phone[-4:]}"
    registration_requests[req_id] = {
        "id": req_id,
        "phone": phone,
        "data": provider_data,
        "approved": False,
        "created_at": time.time(),
        "expires_at": time.time() + REGISTRATION_TIMEOUT,
    }

    send_msg(
        phone,
        "أرجو الاشتراك من أجل السماح بتلقي الطلبات ✨\n\n"
        "تم استلام طلب تسجيلك، وبعد تأكيد الاشتراك سيتم اعتمادك كمقدم خدمة."
    )

    send_group(
        SUBSCRIBERS_GROUP,
        f"📥 طلب اشتراك جديد\n"
        f"رقم الطلب: {req_id}\n"
        f"الاسم/النشاط: {provider_data.get('name', '')}\n"
        f"رقم الهوية: {provider_data.get('identity', '')}\n"
        f"اللغة: {provider_data.get('language_name', '')}\n"
        f"المدينة: {provider_data.get('city', '')}\n"
        f"التخصص: {provider_data.get('specialty', '')}\n"
        f"الرقم: {phone}\n\n"
        f"أي تفاعل على هذه الرسالة داخل القروب يعني اعتماد المشترك.\n"
        f"وللدقة يمكن إرسال: {req_id}"
    )

    def expire_request(local_req_id=req_id):
        time.sleep(REGISTRATION_TIMEOUT)
        req = registration_requests.get(local_req_id)
        if not req or req.get("approved"):
            return
        registration_requests.pop(local_req_id, None)
        send_msg(phone, "لم يتم اعتماد طلبك حالياً. يمكنك إعادة المحاولة بعد 24 ساعة.")
        log_event("رفض_تسجيل_مقدم", phone, "انتهت مهلة اعتماد الاشتراك", local_req_id)

    t = threading.Thread(target=expire_request)
    t.daemon = True
    t.start()


def approve_registration_from_group(sender_phone, text):
    req = None
    for req_id, item in registration_requests.items():
        if req_id in text and not item.get("approved") and time.time() < item.get("expires_at", 0):
            req = item
            break

    if req is None:
        req = get_oldest_pending_registration()

    if req is None:
        return

    applicant_phone = req["phone"]
    provider_data = req["data"]
    provider_data["approved_by"] = sender_phone
    provider_data["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    registered_providers[applicant_phone] = provider_data
    save_providers()

    req["approved"] = True
    registration_requests.pop(req["id"], None)

    log_event(
        "تسجيل_مقدم",
        applicant_phone,
        f"{provider_data.get('name', '')} | {provider_data.get('identity', '')} | {provider_data.get('language_name', '')} | {provider_data.get('city', '')} | {provider_data.get('specialty', '')} | اعتماد: {sender_phone}",
        req["id"],
    )

    send_msg(
        applicant_phone,
        f"تم اعتمادك كمقدم خدمة ✅\n\n"
        f"الاسم/النشاط: {provider_data.get('name', '')}\n"
        f"رقم الهوية: {provider_data.get('identity', '')}\n"
        f"اللغة: {provider_data.get('language_name', '')}\n"
        f"المدينة: {provider_data.get('city', '')}\n"
        f"التخصص: {provider_data.get('specialty', '')}\n\n"
        f"أرسل 1 لاستلام أي طلب."
    )

    send_group(
        SUBSCRIBERS_GROUP,
        f"✅ تم اعتماد المشترك\n"
        f"رقم الطلب: {req['id']}\n"
        f"الاسم/النشاط: {provider_data.get('name', '')}\n"
        f"الرقم: {applicant_phone}\n"
        f"بواسطة: {sender_phone}"
    )

# ==========================================
# القوائم
# ==========================================
def menu_city(phone):
    send_msg(phone,
        "مرحباً بك في مذكرة سلمان 📒\n\n"
        "منصتك الذكية للتواصل مع\n"
        "مقدمي الخدمات في مدينتك\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "تريد خدمة؟ اختر مدينتك:\n"
        "1 - حائل 📍\n"
        "(مدن أخرى قريباً 🔜)\n\n"
        "تريد تسجيل نشاطك التجاري؟\n"
        "أرسل: 2\n\n"
        "للشكاوى والاقتراحات\n"
        "أرسل: 3"
    )

def menu_city_more(phone):
    send_msg(phone,
        "اختر مدينتك:\n\n"
        "3  - جدة\n"
        "4  - مكة المكرمة\n"
        "5  - المدينة المنورة\n"
        "6  - الدمام\n"
        "7  - الخبر\n"
        "8  - الأحساء\n"
        "9  - تبوك\n"
        "10 - أبها\n"
        "11 - القصيم\n"
        "12 - خميس مشيط\n"
        "13 - الطائف\n"
        "14 - ينبع\n"
        "15 - الجبيل\n"
        "16 - القطيف\n"
        "17 - نجران\n"
        "18 - جازان\n"
        "19 - سكاكا\n"
        "20 - حفر الباطن\n"
        "21 - عرعر\n"
        "22 - الجوف\n"
        "23 - رفحاء\n"
        "24 - الباحة\n"
        "25 - عسير\n\n"
        "0  - رجوع ↩️\n\n"
        "ارسل رقم مدينتك"
    )

def menu_service(phone, city):
    lines = []
    for num, svc in SERVICES.items():
        count = count_providers(city, svc)
        lines.append(f"{num.rjust(2)} - {svc} ({count} مقدم)")
    send_msg(phone,
        f"اخترت: {city}\n\n"
        "اختر الخدمة:\n\n" +
        "\n".join(lines) +
        "\n\n0 - رجوع ↩️\n\n"
        "ارسل رقم الخدمة"
    )

def menu_admin_options(phone):
    send_msg(phone,
        "اختر من القائمة:\n\n"
        "1 - تواصل مع الإدارة\n"
        "2 - شكوى\n"
        "0 - رجوع ↩️"
    )

def menu_provider_main(phone, provider):
    send_msg(phone,
        f"مرحباً {provider.get('name', '')} 👋\n\n"
        "اختر من القائمة:\n\n"
        "1 - طلب جديد (كعميل)\n"
        "2 - حسابي\n"
        "3 - تواصل مع الإدارة"
    )

def menu_provider_account(phone, provider):
    expiry = provider.get("expiry", "غير محدد")
    status = "مفعّل ✅" if provider.get("status") == "active" else "موقوف ⚠️"
    send_msg(phone,
        f"معلومات حسابك:\n\n"
        f"الاسم: {provider.get('name', '')}\n"
        f"المدينة: {provider.get('city', '')}\n"
        f"التخصص: {provider.get('specialty', '')}\n"
        f"الحالة: {status}\n"
        f"الاشتراك: {expiry}\n\n"
        f"1 - رجوع"
    )

def client_terms(phone):
    send_msg(phone,
        "قبل المتابعة يرجى قراءة الشروط:\n\n"
        "1️⃣ المنصة وسيط إلكتروني فقط\n"
        "ولا تتحمل مسؤولية جودة الخدمة\n\n"
        "2️⃣ يُمنع استخدام ألفاظ مسيئة\n"
        "أو التحرش أو التهديد\n\n"
        "3️⃣ في حال الإساءة يحق للمنصة\n"
        "إيقاف حسابك وإحالتك للجهات القانونية\n\n"
        "4️⃣ بياناتك الشخصية محفوظة\n"
        "ولن تُشارك مع أي طرف ثالث\n\n"
        "5️⃣ أي نزاع يُحل عبر الجهات المختصة\n"
        "في المملكة العربية السعودية\n\n"
        "هل توافق؟\n\n"
        "1 - أوافق ✅\n"
        "2 - لا أوافق ❌\n"
        "0 - رجوع ↩️"
    )

def provider_terms(phone):
    send_msg(phone,
        "أهلاً بك في مذكرة سلمان 🎉\n\n"
        "منصتنا تربطك بعملاء محتملين\n"
        "في مدينتك بشكل يومي ومستمر\n\n"
        "━━━━━━━━━━━━━━\n"
        "📋 الشروط والأحكام\n"
        "━━━━━━━━━━━━━━\n\n"
        "1️⃣ المنصة وسيط إلكتروني فقط\n"
        "أنت مسؤول عن جودة خدمتك\n\n"
        "2️⃣ الاشتراك الشهري: 20 ريال\n"
        "يُدفع مسبقاً قبل بدء الخدمة\n"
        "قابل للتغيير مع إشعار مسبق\n\n"
        "3️⃣ بيانات العملاء سرية تماماً\n"
        "يُحظر مشاركتها مع أي طرف\n\n"
        "4️⃣ نظام الشكاوى:\n"
        "شكوى 1 ← تحذير رسمي ⚠️\n"
        "شكوى 2 ← تحذير أخير ⚠️⚠️\n"
        "شكوى 3 ← إيقاف سنة 🚫\n"
        "الاحتيال ← إيقاف نهائي\n\n"
        "5️⃣ عدم الاستجابة للعميل\n"
        "يُسجَّل كشكوى تلقائياً\n\n"
        "━━━━━━━━━━━━━━\n"
        "1 - أوافق وأريد التسجيل ✅\n"
        "2 - لا أوافق ❌\n"
        "0 - رجوع ↩️\n"
        "━━━━━━━━━━━━━━"
    )

# ==========================================
# تسجيل مقدم الخدمة
# ==========================================
def handle_provider_registration(phone, msg):
    session = provider_sessions.get(phone, {})
    step = session.get("step", "")

    if step == "language":
        if msg == "0":
            provider_sessions.pop(phone, None)
            user_sessions[phone] = {"step": "start"}
            menu_city(phone)
            return

        if msg not in LANGUAGES:
            send_msg(phone, "أرسل 1 أو 2 أو 3 لتحديد اللغة")
            return

        lang = LANGUAGES[msg]
        provider_sessions[phone] = {
            "step": "terms",
            "language": lang["code"],
            "language_name": lang["name"],
        }
        provider_terms(phone)

    elif step == "terms":
        if msg == "0":
            provider_sessions[phone] = {"step": "language"}
            menu_provider_language(phone)
            return

        if msg == "1":
            provider_sessions[phone].update({"step": "name"})
            send_msg(phone, "سجل اسمك أو اسم نشاطك التجاري:\n\n0 - رجوع ↩️")
        elif msg == "2":
            send_msg(phone, "شكراً لاهتمامك. نتمنى انضمامك لاحقاً.")
            provider_sessions.pop(phone, None)
        else:
            provider_terms(phone)

    elif step == "name":
        if msg == "0":
            provider_sessions[phone].update({"step": "terms"})
            provider_terms(phone)
            return

        provider_sessions[phone].update({
            "step": "identity",
            "name": msg.strip(),
        })
        send_msg(phone, "أرسل رقم الهوية أو الإقامة:\n\n0 - رجوع ↩️")

    elif step == "identity":
        if msg == "0":
            provider_sessions[phone].update({"step": "name"})
            send_msg(phone, "سجل اسمك أو اسم نشاطك التجاري:\n\n0 - رجوع ↩️")
            return

        identity = msg.strip()
        if not identity.isdigit() or len(identity) != 10:
            send_msg(phone, "رقم الهوية أو الإقامة يجب أن يكون 10 أرقام.\n\n0 - رجوع ↩️")
            return

        provider_sessions[phone].update({
            "step": "city",
            "identity": identity,
        })
        menu_city(phone)

    elif step == "city":
        if msg == "0":
            provider_sessions[phone].update({"step": "identity"})
            send_msg(phone, "أرسل رقم الهوية أو الإقامة:\n\n0 - رجوع ↩️")
            return

        if msg == "3":
            provider_sessions[phone].update({"step": "city_more"})
            menu_city_more(phone)
            return

        if msg not in ["1", "2"]:
            send_msg(phone, "الرجاء إرسال 1 أو 2 أو 3")
            return

        provider_sessions[phone].update({
            "step": "specialty",
            "city": CITIES[msg],
        })
        send_provider_specialty_menu(phone)

    elif step == "city_more":
        if msg == "0":
            provider_sessions[phone].update({"step": "city"})
            menu_city(phone)
            return

        if msg not in CITIES or msg in ["1", "2"]:
            send_msg(phone, "الرجاء إرسال رقم من 3 إلى 25")
            return

        provider_sessions[phone].update({
            "step": "specialty",
            "city": CITIES[msg],
        })
        send_provider_specialty_menu(phone)

    elif step == "specialty":
        if msg == "0":
            provider_sessions[phone].update({"step": "city"})
            menu_city(phone)
            return

        if msg not in SERVICES:
            send_msg(phone, "الرجاء إرسال رقم من 1 إلى 8 أو 0 للرجوع")
            return

        if not can_start_registration(phone):
            remaining = format_remaining_hours(registration_cooldown_remaining(phone))
            send_msg(phone, f"يمكنك تقديم طلب تسجيل واحد فقط كل 24 ساعة. المتبقي: {remaining}")
            provider_sessions.pop(phone, None)
            return

        provider_data = {
            "name": session.get("name", ""),
            "identity": session.get("identity", ""),
            "language": session.get("language", "ar"),
            "language_name": session.get("language_name", "العربية"),
            "city": session.get("city", ""),
            "specialty": SERVICES[msg],
            "status": "active",
            "expiry": "",
            "registered": datetime.now().strftime("%Y-%m-%d"),
        }

        send_registration_request(phone, provider_data)
        provider_sessions.pop(phone, None)

# ==========================================
# قائمة مقدم الخدمة# ==========================================
# قائمة مقدم الخدمة# ==========================================
# قائمة مقدم الخدمة
# ==========================================
def handle_provider_menu(phone, msg, provider):
    session = user_sessions.get(phone, {"step": "provider_main"})
    step    = session.get("step", "provider_main")

    if step == "provider_main":
        if msg == "1":
            user_sessions[phone] = {"step": "city"}
            menu_city(phone)
        elif msg == "2":
            user_sessions[phone] = {"step": "provider_account"}
            menu_provider_account(phone, provider)
        elif msg == "3":
            user_sessions[phone] = {"step": "provider_contact"}
            send_msg(phone, "اكتب رسالتك للإدارة:\n\n0 - رجوع ↩️")
        else:
            menu_provider_main(phone, provider)

    elif step == "provider_account":
        user_sessions[phone] = {"step": "provider_main"}
        menu_provider_main(phone, provider)

    elif step == "provider_contact":
        if msg == "0":
            user_sessions[phone] = {"step": "provider_main"}
            menu_provider_main(phone, registered_providers[phone])
            return
        send_group(ADMIN_GROUP,
            f"📞 رسالة من مقدم خدمة\n"
            f"الاسم: {provider.get('name', '')}\n"
            f"الرقم: {phone}\n"
            f"الرسالة: {msg}"
        )
        send_msg(phone, "تم إرسال رسالتك ✅\nسيتم التواصل معك قريباً 🙏")
        user_sessions[phone] = {"step": "provider_main"}
        menu_provider_main(phone, provider)

# ==========================================
# إنشاء الطلب — نظام الطابور
# ==========================================
def create_order(phone, city, service, description=""):
    order_counter[0] += 1
    oid = f"MS-{order_counter[0]}"

    matched = [
        p for p, d in registered_providers.items()
        if d.get("city") == city
        and d.get("specialty") == service
        and d.get("status") == "active"
        and check_subscription(d)
    ]

    pending_orders[oid] = {
        "phone":            phone,
        "city":             city,
        "service":          service,
        "description":      description,
        "attempts":         1,
        "blocked":          [],
        "taken":            False,
        "providers":        matched,
        "created":          datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    save_counter()
    save_orders()
    log_event("طلب_جديد", phone, f"{city} | {service} | {description}", oid)

    user_sessions[phone] = {"step": "waiting", "order_id": oid}

    send_msg(phone,
        f"تم استلام طلبك ✅\n"
        f"رقم الطلب: {oid}\n\n"
        f"سيتم التواصل معك خلال 5 دقائق"
    )

    if not matched:
        send_group(ADMIN_GROUP,
            f"⚠️ لا يوجد مقدم خدمة\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {city}\n"
            f"الخدمة: {service}\n"
            f"العميل: {phone}"
        )
        def ask_wait_or_cancel_new(cp=phone, oid=oid):
            time.sleep(5 * 60)
            if oid not in pending_orders:
                return
            if pending_orders.get(oid, {}).get("taken"):
                return
            user_sessions[cp] = {"step": "waiting_choice", "order_id": oid}
            send_msg(cp,
                "لم نجد لك مقدم خدمة حتى الآن 😔\n\n"
                "1 - انتظار ⏳\n"
                "2 - إلغاء الطلب ❌"
            )
        threading.Thread(target=ask_wait_or_cancel_new).start()
        return

    broadcast_order(oid)

def broadcast_order(oid):
    """إرسال الطلب لكل المقدمين المتاحين في نفس الوقت"""
    if oid not in pending_orders:
        return
    od       = pending_orders[oid]
    providers = od.get("providers", [])
    blocked  = od.get("blocked", [])
    cp       = od["phone"]

    # المقدمون المتاحون (غير محظورين وغير في cooldown)
    available = [
        p for p in providers
        if p not in blocked

    ]

    if not available:
        # لا يوجد مقدم متاح
        send_group(ADMIN_GROUP,
            f"⚠️ طلب بدون مستجيب\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n"
            f"العميل: {cp}"
        )

    desc = f"الوصف: {od['description']}\n" if od.get("description") else ""

    # إرسال لكل المقدمين في نفس الوقت
    for p in available:
        send_msg(p,
            f"طلب جديد 🔔\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n"
            f"{desc}"
            f"━━━━━━━━━━━━━━\n"
            f"لاستلام الطلب أرسل: 1\n\n"
            f"To accept send: 1\n\n"
            f"آرڈر لینے کے لیے بھیجیں: 1\n"
            f"━━━━━━━━━━━━━━"
        )
        time.sleep(0.3)

    # بعد 5 دقائق — لو لم يُقبل الطلب اسأل العميل
    def check_after_5min(cp=cp, oid=oid):
        time.sleep(5 * 60)
        if oid not in pending_orders:
            return
        if pending_orders.get(oid, {}).get("taken"):
            return
        user_sessions[cp] = {"step": "waiting_choice", "order_id": oid}
        send_msg(cp,
            "لم نجد لك مقدم خدمة حتى الآن 😔\n\n"
            "1 - انتظار ⏳\n"
            "2 - إلغاء الطلب ❌"
        )
    threading.Thread(target=check_after_5min).start()


# ==========================================
# استلام الطلب من مقدم الخدمة
# ==========================================
def handle_provider_accept(phone):
    # البحث عن طلب مرسل لهذا المقدم
    for oid, od in list(pending_orders.items()):
        if od.get("taken"):
            continue
        # المقدم يجب أن يكون ضمن قائمة المقدمين للطلب وغير محظور
        if phone not in od.get("providers", []):
            continue
        if phone in od.get("blocked", []):
            continue

        cp = od["phone"]
        od["taken"] = True
        od["blocked"].append(phone)
        log_event("قبول_طلب", phone, f"مقدم قبل الطلب | عميل: {cp}", oid)

        provider_name = registered_providers.get(phone, {}).get("name", "مقدم الخدمة")

        # رسالة للعميل — بيانات مقدم الخدمة
        send_msg(cp,
            f"ابشر به 🎉\n\n"
            f"تم قبول طلبك رقم {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n\n"
            f"مقدم الخدمة: {provider_name}\n"
            f"للتواصل: {phone}"
        )

        # رسالة لمقدم الخدمة
        send_msg(phone,
            f"تم تأكيد استلامك للطلب {oid} ✅\n"
            f"سيتواصل معك العميل قريباً"
        )

        # تقييم بعد دقيقة
        def send_rating(cp=cp):
            time.sleep(60)
            send_msg(cp,
                "كيف كانت تجربتك مع مقدم الخدمة؟\n\n"
                "1 - ممتاز تم الاتفاق ✅\n"
                "2 - لم يتم الاتفاق (إعادة)\n"
                "3 - تواصل مع الإدارة"
            )
        threading.Thread(target=send_rating).start()
        user_sessions[cp] = {"step": "provider_sent", "order_id": oid}
        save_orders()
        return

    send_msg(phone, "لا يوجد طلب متاح لك الآن ⏳")

# ==========================================
# إعادة الطلب
# ==========================================
def resend_order(phone, oid, reason, price=None):
    if oid not in pending_orders:
        return
    od = pending_orders[oid]
    od["attempts"] += 1
    od["taken"] = False
    if price:
        od["last_price"] = price

    attempts = od["attempts"]
    warning  = "\nتنبيه: هذه آخر محاولة ⚠️" if attempts == 3 else ""
    send_msg(phone,
        f"تم إعادة طلبك\n"
        f"المحاولة {attempts} من 3{warning}\n"
        f"سيتم التواصل معك خلال 5 دقائق"
    )
    user_sessions[phone] = {"step": "waiting", "order_id": oid}
    save_orders()
    broadcast_order(oid)

# ==========================================
# سيناريو العميل
# ==========================================
def handle_customer(phone, msg):
    blocked, remaining = is_blocked(phone)
    if blocked:
        send_msg(phone, f"حسابك موقوف مؤقتاً\nالمتبقي: {remaining} دقيقة ⏱️")
        return

    timed_out = check_timeout(phone)
    if timed_out:
        session = {"step": "start"}
        user_sessions[phone] = session
    else:
        session = user_sessions.get(phone, {"step": "start"})

    step = session.get("step", "start")

    if step == "start":
        log_event("رسالة_جديدة", phone, "عميل جديد بدأ المحادثة")
        menu_city(phone)
        user_sessions[phone] = {"step": "city"}

    elif step == "city":
        if msg == "1":
            city = "حائل"
            log_event("اختيار_مدينة", phone, f"اختار: {city}")
            user_sessions[phone] = {"step": "service", "city": city}
            menu_service(phone, city)
        elif msg == "2":
            if not can_start_registration(phone):
                remaining = format_remaining_hours(registration_cooldown_remaining(phone))
                send_msg(phone, f"يمكنك تقديم طلب تسجيل واحد فقط كل 24 ساعة. المتبقي: {remaining}")
                user_sessions[phone] = {"step": "start"}
                return
            provider_sessions[phone] = {"step": "language"}
            menu_provider_language(phone)
            user_sessions[phone] = {"step": "start"}
        elif msg == "3":
            # شكاوى واقتراحات
            user_sessions[phone] = {"step": "complaint"}
            send_msg(phone, "اكتب شكواك أو اقتراحك وسيتم مراجعته فوراً:\n\n0 - رجوع ↩️")
        else:
            send_msg(phone,
                "الرجاء ارسال:\n"
                "1 - لطلب خدمة\n"
                "2 - للتسجيل كمقدم خدمة\n"
                "3 - للشكاوى والاقتراحات"
            )

    elif step == "city_more":
        if msg == "0":
            user_sessions[phone] = {"step": "city"}
            menu_city(phone)
            return
        if msg not in CITIES or msg in ["1", "2"]:
            send_msg(phone, "الرجاء ارسال رقم من 3 الى 25")
            return
        city = CITIES[msg]
        log_event("اختيار_مدينة", phone, f"اختار: {city}")
        user_sessions[phone] = {"step": "service", "city": city}
        menu_service(phone, city)

    elif step == "service":
        city = session.get("city")
        if msg == "0":
            user_sessions[phone] = {"step": "city"}
            menu_city(phone)
            return
        if msg in SERVICES:
            service = SERVICES[msg]
            log_event("اختيار_خدمة", phone, f"{city} | {service}")
            user_sessions[phone] = {"step": "description", "city": city, "service": service}
            send_msg(phone,
                f"اخترت: {service} في {city}\n\n"
                "اكتب وصفاً قصيراً عن طلبك:\n"
                "(مثال: أحتاج كهربائي لإصلاح عطل في المنزل)\n\n"
                "0 - رجوع ↩️"
            )
        else:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 8 أو 0 للرجوع")

    elif step == "description":
        city        = session.get("city")
        service     = session.get("service")
        if msg == "0":
            user_sessions[phone] = {"step": "service", "city": city}
            menu_service(phone, city)
            return
        description = msg
        if phone not in registered_clients:
            user_sessions[phone] = {
                "step": "terms",
                "city": city,
                "service": service,
                "description": description
            }
            client_terms(phone)
        else:
            create_order(phone, city, service, description)

    elif step == "terms":
        city        = session.get("city")
        service     = session.get("service")
        description = session.get("description", "")
        if msg == "0":
            user_sessions[phone] = {"step": "description", "city": city, "service": service}
            send_msg(phone,
                f"اخترت: {service} في {city}\n\n"
                "اكتب وصفاً قصيراً عن طلبك:\n"
                "(مثال: أحتاج كهربائي لإصلاح عطل في المنزل)\n\n"
                "0 - رجوع ↩️"
            )
            return
        if msg == "1":
            registered_clients.add(phone)
            save_clients()
            create_order(phone, city, service, description)
        elif msg == "2":
            send_msg(phone, "شكراً لك\nنتمنى خدمتك في وقت آخر 🌟")
            user_sessions[phone] = {"step": "start"}
        else:
            client_terms(phone)

    elif step == "admin_menu":
        city = session.get("city")
        if msg == "0":
            user_sessions[phone] = {"step": "service", "city": city}
            menu_service(phone, city)
            return
        if msg == "1":
            send_msg(phone, "سيتواصل معك فريق الإدارة قريباً 🙏")
            send_group(ADMIN_GROUP, f"📞 طلب تواصل\nرقم العميل: {phone}")
            user_sessions[phone] = {"step": "start"}
        elif msg == "2":
            user_sessions[phone] = {"step": "complaint"}
            send_msg(phone, "اكتب شكواك وسيتم مراجعتها فوراً:\n\n0 - رجوع ↩️")
        else:
            menu_admin_options(phone)

    elif step == "complaint":
        if msg == "0":
            user_sessions[phone] = {"step": "admin_menu"}
            menu_admin_options(phone)
            return
        log_event("شكوى", phone, msg)
        send_group(ADMIN_GROUP, f"🚨 شكوى\nرقم العميل: {phone}\nالشكوى: {msg}")
        send_msg(phone, "تم استلام شكواك ✅\nسيتم التواصل معك قريباً")
        user_sessions[phone] = {"step": "start"}

    elif step == "waiting":
        # تجاهل كامل — لا رد
        return

    elif step == "waiting_choice":
        oid = session.get("order_id")
        if msg == "1":
            # ينتظر — نعيد البث لكل المقدمين
            user_sessions[phone] = {"step": "waiting", "order_id": oid}
            send_msg(phone, "شكراً لصبرك ⏳\nسنواصل البحث عن مقدم خدمة لك")
            if oid in pending_orders:
                pending_orders[oid]["blocked"] = []
                broadcast_order(oid)
        elif msg == "2":
            # إلغاء الطلب
            log_event("إلغاء_طلب", phone, "العميل ألغى بعد انتهاء الوقت", oid)
            pending_orders.pop(oid, None)
            save_orders()
            user_sessions[phone] = {"step": "start"}
            send_msg(phone, "تم إلغاء طلبك ✅\nيمكنك إرسال طلب جديد في أي وقت")
        else:
            send_msg(phone,
                "لم نجد لك مقدم خدمة حتى الآن\n\n"
                "1 - انتظار ⏳\n"
                "2 - إلغاء الطلب ❌"
            )

    elif step == "provider_sent":
        oid = session.get("order_id")
        od  = pending_orders.get(oid, {})

        if msg == "1":
            send_msg(phone, "ممتاز! نتمنى لك تجربة رائعة مع مذكرة سلمان 🌟")
            log_event("اتفاق_ناجح", phone, "تم الاتفاق مع مقدم الخدمة", oid)
            pending_orders.pop(oid, None)
            save_orders()
            user_sessions[phone] = {"step": "start"}

        elif msg == "2":
            attempts = od.get("attempts", 1)
            if attempts >= 3:
                blocked_users[phone] = time.time() + 15 * 60
                log_event("حظر_مؤقت", phone, "تم الحظر 15 دقيقة بعد 3 محاولات فاشلة", oid)
                send_msg(phone, "تم استنفاد المحاولات\nحسابك موقوف 15 دقيقة ⏱️")
                pending_orders.pop(oid, None)
                save_orders()
                user_sessions[phone] = {"step": "start"}
            else:
                user_sessions[phone] = {"step": "reason", "order_id": oid}
                send_msg(phone,
                    "ما سبب عدم الاتفاق؟\n\n"
                    "1 - السعر مرتفع\n"
                    "2 - لم يتجاوب\n"
                    "3 - سبب آخر\n"
                    "0 - رجوع ↩️"
                )

        elif msg == "3":
            send_msg(phone, "نأسف لما تمر به\nسيتواصل معك فريق الإدارة قريباً 🙏")
            send_group(ADMIN_GROUP,
                f"🚨 شكوى عميل\nرقم الطلب: {oid}\nرقم العميل: {phone}"
            )
            user_sessions[phone] = {"step": "start"}
        else:
            send_msg(phone,
                "كيف كانت تجربتك؟\n\n"
                "1 - ممتاز تم الاتفاق ✅\n"
                "2 - لم يتم الاتفاق\n"
                "3 - تواصل مع الإدارة"
            )

    elif step == "reason":
        oid = session.get("order_id")
        if msg == "0":
            user_sessions[phone] = {"step": "provider_sent", "order_id": oid}
            send_msg(phone,
                "كيف كانت تجربتك مع مقدم الخدمة؟\n\n"
                "1 - ممتاز تم الاتفاق ✅\n"
                "2 - لم يتم الاتفاق (إعادة)\n"
                "3 - تواصل مع الإدارة"
            )
            return
        if msg == "1":
            user_sessions[phone] = {"step": "price", "order_id": oid}
            send_msg(phone, "كم السعر المعروض؟ (بالريال)")
        elif msg == "2":
            resend_order(phone, oid, "لم يتجاوب مقدم الخدمة")
        elif msg == "3":
            user_sessions[phone] = {"step": "custom_reason", "order_id": oid}
            send_msg(phone, "اكتب سبب عدم الاتفاق:")
        else:
            send_msg(phone, "1 - السعر مرتفع\n2 - لم يتجاوب\n3 - سبب آخر")

    elif step == "price":
        resend_order(phone, session.get("order_id"), "السعر مرتفع", price=msg)

    elif step == "custom_reason":
        resend_order(phone, session.get("order_id"), msg)

# ==========================================
# التحكم — رسالة خاصة من الأدمن
# ==========================================
def handle_control(phone, msg):
    session = control_sessions.get(phone, {"step": "start"})
    step    = session.get("step", "start")

    if msg == "تحكم" or step in ["start", ""]:
        control_sessions[phone] = {"step": "main_menu"}
        send_msg(phone,
            "لوحة التحكم 🎮\n\n"
            "1 - رسالة جماعية للمقدمين 📢\n"
            "2 - رسالة جماعية للعملاء 👥\n"
            "3 - إدارة مقدمي الخدمة ⚙️\n"
            "4 - إدارة العملاء 👤\n"
            "5 - تحميل البيانات 📊\n"
            "0 - إلغاء ❌"
        )
        return

    # 0 يُعالج داخل كل step لوحده
    

    # ─── القائمة الرئيسية ───
    if step == "main_menu":
        if msg == "1":
            control_sessions[phone] = {"step": "choose"}
            send_msg(phone,
                "اختر المقدمين المستهدفين:\n\n"
                "1 - الخدمات الهندسية\n"
                "2 - الخدمات العقارية\n"
                "3 - الخدمات الطلابية\n"
                "4 - مناديب التوصيل\n"
                "5 - شاليهات\n"
                "6 - صهريج مياه\n"
                "7 - اسطوانات الغاز\n"
                "8 - سطحات\n"
                "━━━━━━━━━━━━━━\n"
                "9  - مدينة محددة\n"
                "10 - الجميع 📢\n"
                "0  - إلغاء ❌"
            )
        elif msg == "2":
            count = len(registered_clients)
            control_sessions[phone] = {"step": "write_clients"}
            send_msg(phone, f"عدد العملاء المسجلين: {count}\n\nاكتب رسالتك:\n(0 للإلغاء)")
        elif msg == "3":
            control_sessions[phone] = {"step": "manage_providers"}
            send_msg(phone,
                "إدارة مقدمي الخدمة ⚙️\n\n"
                "1 - عرض قائمة المقدمين\n"
                "2 - إيقاف مقدم\n"
                "3 - تفعيل مقدم\n"
                "4 - حذف مقدم\n"
                "0 - رجوع"
            )
        elif msg == "4":
            control_sessions[phone] = {"step": "manage_clients"}
            send_msg(phone,
                "إدارة العملاء 👤\n\n"
                "1 - عرض قائمة العملاء\n"
                "2 - حذف عميل\n"
                "3 - رفع حظر عميل\n"
                "0 - رجوع ↩️"
            )
        elif msg == "5":
            control_sessions[phone] = {"step": "export_menu"}
            send_msg(phone,
                "تحميل البيانات 📊\n\n"
                "1 - بيانات مقدمي الخدمة\n"
                "2 - بيانات العملاء\n"
                "3 - كل البيانات\n"
                "0 - رجوع ↩️"
            )
        else:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 5")
        return

    # ─── تحميل البيانات ───
    if step == "export_menu":
        base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://absherbh-bot.onrender.com")
        key      = EXPORT_SECRET
        if msg == "1":
            send_msg(phone,
                f"رابط تحميل بيانات المقدمين 📋\n\n"
                f"{base_url}/export?key={key}&type=providers\n\n"
                f"المقدمون المسجلون: {len(registered_providers)}"
            )
            control_sessions[phone] = {"step": "export_menu"}
        elif msg == "2":
            send_msg(phone,
                f"رابط تحميل بيانات العملاء 👥\n\n"
                f"{base_url}/export?key={key}&type=clients\n\n"
                f"العملاء المسجلون: {len(registered_clients)}"
            )
            control_sessions[phone] = {"step": "export_menu"}
        elif msg == "3":
            send_msg(phone,
                f"رابط تحميل كل البيانات 📊\n\n"
                f"{base_url}/export?key={key}\n\n"
                f"المقدمون: {len(registered_providers)} | العملاء: {len(registered_clients)}"
            )
            control_sessions[phone] = {"step": "export_menu"}
        elif msg == "0":
            control_sessions[phone] = {"step": "main_menu"}
            send_msg(phone,
                "لوحة التحكم 🎮\n\n"
                "1 - رسالة جماعية للمقدمين 📢\n"
                "2 - رسالة جماعية للعملاء 👥\n"
                "3 - إدارة مقدمي الخدمة ⚙️\n"
                "4 - إدارة العملاء 👤\n"
                "5 - تحميل البيانات 📊\n"
                "0 - إلغاء ❌"
            )
        else:
            send_msg(phone, "الرجاء ارسال 1 أو 2 أو 3")
        return

    # ─── رسالة جماعية للعملاء ───
    if step == "write_clients":
        if msg == "0":
            control_sessions[phone] = {"step": "main_menu"}
            send_msg(phone,
                "لوحة التحكم 🎮\n\n"
                "1 - رسالة جماعية للمقدمين 📢\n"
                "2 - رسالة جماعية للعملاء 👥\n"
                "3 - إدارة مقدمي الخدمة ⚙️\n"
                "0 - إلغاء ❌"
            )
            return
        targets = list(registered_clients)
        count   = 0
        for c in targets:
            send_msg(c, msg)
            count += 1
            time.sleep(0.5)
        send_msg(phone, f"✅ تم الإرسال لـ {count} عميل")
        control_sessions[phone] = {"step": "start"}
        return

    # ─── إدارة المقدمين ───
    if step == "manage_providers":
        if msg == "1":
            if not registered_providers:
                send_msg(phone, "لا يوجد مقدمو خدمة مسجلون")
                control_sessions[phone] = {"step": "start"}
                return
            lines = []
            for p, d in registered_providers.items():
                status = "✅" if d.get("status") == "active" else "⚠️"
                lines.append(f"{status} {d.get('name','')} | {d.get('specialty','')} | {d.get('city','')} | {p}")
            # إرسال على دفعات (واتساب يرفض الرسائل الطويلة جداً)
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) > 3000:
                    send_msg(phone, chunk)
                    chunk = ""
                    time.sleep(0.5)
                chunk += line + "\n"
            if chunk:
                send_msg(phone, chunk)
            control_sessions[phone] = {"step": "start"}

        elif msg in ["2", "3", "4"]:
            action_map = {"2": "إيقاف", "3": "تفعيل", "4": "حذف"}
            control_sessions[phone] = {"step": "provider_action", "action": msg}
            send_msg(phone,
                f"أدخل رقم جوال المقدم الذي تريد {action_map[msg]}ه:\n"
                "(بدون + مثال: 966501234567)\n\n"
                "0 - رجوع"
            )

        elif msg == "0":
            control_sessions[phone] = {"step": "main_menu"}
            send_msg(phone,
                "لوحة التحكم 🎮\n\n"
                "1 - رسالة جماعية للمقدمين 📢\n"
                "2 - رسالة جماعية للعملاء 👥\n"
                "3 - إدارة مقدمي الخدمة ⚙️\n"
                "0 - إلغاء ❌"
            )
        else:
            send_msg(phone, "الرجاء ارسال 1 أو 2 أو 3 أو 4")
        return

    if step == "provider_action":
        if msg == "0":
            control_sessions[phone] = {"step": "manage_providers"}
            send_msg(phone,
                "إدارة مقدمي الخدمة ⚙️\n\n"
                "1 - عرض قائمة المقدمين\n"
                "2 - إيقاف مقدم\n"
                "3 - تفعيل مقدم\n"
                "4 - حذف مقدم\n"
                "0 - رجوع ↩️"
            )
            return
        action = session.get("action")
        target = msg.strip()
        if target not in registered_providers:
            send_msg(phone, f"الرقم {target} غير موجود في قاعدة البيانات\nتأكد من الرقم وأعد المحاولة")
            return
        name = registered_providers[target].get("name", target)
        if action == "2":
            registered_providers[target]["status"] = "inactive"
            save_providers()
            send_msg(phone, f"✅ تم إيقاف {name}")
            send_msg(target, "تم إيقاف حسابك مؤقتاً من قِبل الإدارة\nللاستفسار تواصل معنا")
        elif action == "3":
            registered_providers[target]["status"] = "active"
            save_providers()
            send_msg(phone, f"✅ تم تفعيل {name}")
            send_msg(target, "تم تفعيل حسابك ✅\nستصلك الطلبات الآن")
        elif action == "4":
            del registered_providers[target]
            save_providers()
            send_msg(phone, f"✅ تم حذف {name}")
            send_msg(target, "تم حذف حسابك من المنصة\nللاستفسار تواصل مع الإدارة")
        control_sessions[phone] = {"step": "manage_providers"}
        send_msg(phone,
            "إدارة مقدمي الخدمة ⚙️\n\n"
            "1 - عرض قائمة المقدمين\n"
            "2 - إيقاف مقدم\n"
            "3 - تفعيل مقدم\n"
            "4 - حذف مقدم\n"
            "0 - رجوع ↩️"
        )
        return

    # ─── إدارة العملاء ───
    if step == "manage_clients":
        if msg == "1":
            if not registered_clients:
                send_msg(phone, "لا يوجد عملاء مسجلون")
                control_sessions[phone] = {"step": "manage_clients"}
                return
            lines = []
            for i, c in enumerate(registered_clients, 1):
                status = "🚫" if c in blocked_users and time.time() < blocked_users[c] else "✅"
                lines.append(f"{status} {i}. {c}")
            chunk = f"عدد العملاء: {len(registered_clients)}\n\n"
            for line in lines:
                if len(chunk) + len(line) > 3000:
                    send_msg(phone, chunk)
                    chunk = ""
                    time.sleep(0.5)
                chunk += line + "\n"
            if chunk:
                send_msg(phone, chunk)
            control_sessions[phone] = {"step": "manage_clients"}
            send_msg(phone,
                "إدارة العملاء 👤\n\n"
                "1 - عرض قائمة العملاء\n"
                "2 - حذف عميل\n"
                "3 - رفع حظر عميل\n"
                "0 - رجوع ↩️"
            )

        elif msg == "2":
            control_sessions[phone] = {"step": "client_action", "action": "delete"}
            send_msg(phone,
                "أدخل رقم العميل الذي تريد حذفه:\n"
                "(بدون + مثال: 966501234567)\n\n"
                "0 - رجوع ↩️"
            )

        elif msg == "3":
            control_sessions[phone] = {"step": "client_action", "action": "unblock"}
            send_msg(phone,
                "أدخل رقم العميل الذي تريد رفع حظره:\n"
                "(بدون + مثال: 966501234567)\n\n"
                "0 - رجوع ↩️"
            )

        elif msg == "0":
            control_sessions[phone] = {"step": "main_menu"}
            send_msg(phone,
                "لوحة التحكم 🎮\n\n"
                "1 - رسالة جماعية للمقدمين 📢\n"
                "2 - رسالة جماعية للعملاء 👥\n"
                "3 - إدارة مقدمي الخدمة ⚙️\n"
                "4 - إدارة العملاء 👤\n"
                "0 - إلغاء ❌"
            )
        else:
            send_msg(phone, "الرجاء ارسال 1 أو 2 أو 3")
        return

    if step == "client_action":
        action = session.get("action")
        if msg == "0":
            control_sessions[phone] = {"step": "manage_clients"}
            send_msg(phone,
                "إدارة العملاء 👤\n\n"
                "1 - عرض قائمة العملاء\n"
                "2 - حذف عميل\n"
                "3 - رفع حظر عميل\n"
                "0 - رجوع ↩️"
            )
            return
        target = msg.strip()
        if action == "delete":
            if target in registered_clients:
                registered_clients.discard(target)
                save_clients()
                blocked_users.pop(target, None)
                user_sessions.pop(target, None)
                send_msg(phone, f"✅ تم حذف العميل {target}")
                send_msg(target, "تم حذف حسابك من المنصة\nللاستفسار تواصل مع الإدارة")
            else:
                send_msg(phone, f"الرقم {target} غير موجود في قائمة العملاء")
        elif action == "unblock":
            if target in blocked_users:
                del blocked_users[target]
                send_msg(phone, f"✅ تم رفع الحظر عن {target}")
                send_msg(target, "تم رفع الحظر عن حسابك ✅\nيمكنك استخدام الخدمة الآن")
            else:
                send_msg(phone, f"الرقم {target} غير محظور أصلاً")
        control_sessions[phone] = {"step": "manage_clients"}
        send_msg(phone,
            "إدارة العملاء 👤\n\n"
            "1 - عرض قائمة العملاء\n"
            "2 - حذف عميل\n"
            "3 - رفع حظر عميل\n"
            "0 - رجوع ↩️"
        )
        return

    # ─── رسالة جماعية للمقدمين ───
    if step == "choose":
        targets = []
        label   = ""

        if msg in SERVICES:
            label   = SERVICES[msg]
            targets = [p for p, d in registered_providers.items() if d.get("specialty") == label]

        elif msg == "9":
            control_sessions[phone] = {"step": "choose_city"}
            send_msg(phone,
                "اختر المدينة:\n\n" +
                "\n".join([f"{k} - {v}" for k, v in CITIES.items()]) +
                "\n\n0 - إلغاء"
            )
            return

        elif msg == "10":
            label   = "الجميع"
            targets = list(registered_providers.keys())

        elif msg == "0":
            control_sessions[phone] = {"step": "main_menu"}
            send_msg(phone,
                "لوحة التحكم 🎮\n\n"
                "1 - رسالة جماعية للمقدمين 📢\n"
                "2 - رسالة جماعية للعملاء 👥\n"
                "3 - إدارة مقدمي الخدمة ⚙️\n"
                "0 - إلغاء ❌"
            )
            return
        else:
            send_msg(phone, "الرجاء ارسال رقم صحيح")
            return

        control_sessions[phone] = {"step": "write", "targets": targets, "label": label}
        send_msg(phone, f"اخترت: {label} ({len(targets)} مقدم)\n\nاكتب رسالتك:\n(0 للإلغاء)")

    elif step == "choose_city":
        if msg == "0":
            control_sessions[phone] = {"step": "choose"}
            send_msg(phone,
                "اختر المقدمين المستهدفين:\n\n"
                "1  - الهندسية\n"
                "2  - العقارية\n"
                "3  - مقاولين\n"
                "4  - الطلابية\n"
                "5  - المحامين\n"
                "6  - مناديب توصيل\n"
                "7  - صهريج مياه\n"
                "8  - اسطوانات غاز\n"
                "9  - سطحات\n"
                "10 - تبريد وتكييف\n"
                "11 - ورش وتشاليح\n"
                "12 - شاليهات\n"
                "━━━━━━━━━━━━━━\n"
                "13 - مدينة محددة\n"
                "14 - الجميع 📢\n"
                "0  - رجوع ↩️"
            )
            return
        if msg not in CITIES:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 25")
            return
        city    = CITIES[msg]
        targets = [p for p, d in registered_providers.items() if d.get("city") == city]
        control_sessions[phone] = {"step": "write", "targets": targets, "label": city}
        send_msg(phone, f"اخترت: {city} ({len(targets)} مقدم)\n\nاكتب رسالتك:\n(0 للإلغاء)")

    elif step == "write":
        if msg == "0":
            control_sessions[phone] = {"step": "choose"}
            send_msg(phone,
                "اختر المقدمين المستهدفين:\n\n"
                "1  - الهندسية\n"
                "2  - العقارية\n"
                "3  - مقاولين\n"
                "4  - الطلابية\n"
                "5  - المحامين\n"
                "6  - مناديب توصيل\n"
                "7  - صهريج مياه\n"
                "8  - اسطوانات غاز\n"
                "9  - سطحات\n"
                "10 - تبريد وتكييف\n"
                "11 - ورش وتشاليح\n"
                "12 - شاليهات\n"
                "━━━━━━━━━━━━━━\n"
                "13 - مدينة محددة\n"
                "14 - الجميع 📢\n"
                "0  - رجوع ↩️"
            )
            return
        targets = session.get("targets", [])
        label   = session.get("label", "")
        count   = 0
        for p in targets:
            send_msg(p, msg)
            count += 1
            time.sleep(0.5)
        send_msg(phone, f"✅ تم الإرسال لـ {count} مقدم في {label}")
        control_sessions[phone] = {"step": "start"}

# ==========================================
# Webhook
# ==========================================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "ok"}), 200

        wtype   = data.get("typeWebhook", "")
        sd      = data.get("senderData", {})
        md      = data.get("messageData", {})
        sender  = sd.get("sender", "")
        chat_id = sd.get("chatId", "")
        mt      = md.get("typeMessage", "")

        if wtype != "incomingMessageReceived":
            return jsonify({"status": "ok"}), 200

        # ✅ رسائل القروبات
        if "@g.us" in chat_id:
            if mt == "textMessage":
                text = md.get("textMessageData", {}).get("textMessage", "")
            elif mt == "extendedTextMessage":
                text = md.get("extendedTextMessageData", {}).get("text", "")
            else:
                return jsonify({"status": "ok"}), 200

            if not text:
                return jsonify({"status": "ok"}), 200

            text = normalize(text)
            sender_phone = sender.replace("@c.us", "")

            if chat_id == SUBSCRIBERS_GROUP:
                print(f"📩 قروب المشتركين | من: {sender_phone} | النص: {text}")
                approve_registration_from_group(sender_phone, text)
                return jsonify({"status": "ok"}), 200

            if chat_id == CONTROL_GROUP:
                print(f"📩 قروب تحكم | من: {sender_phone} | النص: {text}")
                ADMIN_PHONES.add(sender_phone)
                ctrl_session = control_sessions.get(sender_phone, {"step": "start"})
                ctrl_step = ctrl_session.get("step", "start")
                if text == "تحكم" or ctrl_step not in ["start", ""]:
                    handle_control(sender_phone, text)
                return jsonify({"status": "ok"}), 200

            return jsonify({"status": "ok"}), 200

        # رسالة صوتية
        if mt in ["audioMessage", "pttMessage"]:
            phone = sender.replace("@c.us", "")
            send_msg(phone, "عذراً 🎤\nالرجاء إرسال رسالة نصية فقط")
            return jsonify({"status": "ok"}), 200

        # نص
        if mt == "textMessage":
            text = md.get("textMessageData", {}).get("textMessage", "")
        elif mt == "extendedTextMessage":
            text = md.get("extendedTextMessageData", {}).get("text", "")
        else:
            return jsonify({"status": "ok"}), 200

        if not text:
            return jsonify({"status": "ok"}), 200

        text  = normalize(text)
        phone = sender.replace("@c.us", "")

        print(f"📩 رسالة من: [{phone}] | النص: {text}")

        # لو الرقم أدمن مصرح — اعتبره تحكم
        if phone in ADMIN_PHONES:
            ctrl_session = control_sessions.get(phone, {"step": "start"})
            ctrl_step    = ctrl_session.get("step", "start")
            if text == "تحكم" or ctrl_step not in ["start", ""]:
                handle_control(phone, text)
                return jsonify({"status": "ok"}), 200

        # فلتر الأرقام السعودية
        if not phone.startswith("966"):
            send_msg(phone, "عذراً\nهذه الخدمة متاحة للأرقام السعودية فقط 🇸🇦")
            return jsonify({"status": "ok"}), 200

        # جلسة تسجيل مقدم خدمة
        if phone in provider_sessions:
            handle_provider_registration(phone, text)
            return jsonify({"status": "ok"}), 200

        # مقدم خدمة مسجل
        if phone in registered_providers:
            session = user_sessions.get(phone, {"step": "provider_main"})
            step    = session.get("step", "provider_main")
            customer_steps = [
                "city", "city_more", "service", "description", "terms", "waiting",
                "waiting_choice", "provider_sent", "reason", "price", "custom_reason",
                "admin_menu", "complaint"
            ]
            if step in customer_steps:
                handle_customer(phone, text)
            elif text == "1":
                handle_provider_accept(phone)
            else:
                check_timeout(phone)
                user_sessions[phone] = {"step": "provider_main"}
                handle_provider_menu(phone, text, registered_providers[phone])
            return jsonify({"status": "ok"}), 200

        # عميل عادي
        handle_customer(phone, text)

    except Exception as e:
        print(f"Webhook error: {e}")
    return jsonify({"status": "ok"}), 200


@app.route("/export", methods=["GET"])
def export_data():
    key = request.args.get("key", "")
    if key != EXPORT_SECRET:
        return "غير مصرح ❌", 403

    export_type = request.args.get("type", "providers")

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()

        # ── ورقة مقدمي الخدمة ──
        ws1 = wb.active
        ws1.title = "مقدمو الخدمة"
        headers1 = ["الرقم", "الاسم/النشاط", "رقم الهوية", "اللغة", "المدينة", "التخصص", "الحالة", "الاشتراك", "تاريخ التسجيل"]
        for col, h in enumerate(headers1, 1):
            cell = ws1.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1a7a4a")
            cell.alignment = Alignment(horizontal="center")
        for row, (phone, d) in enumerate(registered_providers.items(), 2):
            ws1.cell(row=row, column=1, value=phone)
            ws1.cell(row=row, column=2, value=d.get("name", ""))
            ws1.cell(row=row, column=3, value=d.get("identity", ""))
            ws1.cell(row=row, column=4, value=d.get("language_name", ""))
            ws1.cell(row=row, column=5, value=d.get("city", ""))
            ws1.cell(row=row, column=6, value=d.get("specialty", ""))
            ws1.cell(row=row, column=7, value="نشط" if d.get("status") == "active" else "موقوف")
            ws1.cell(row=row, column=8, value=d.get("expiry", "غير محدد"))
            ws1.cell(row=row, column=9, value=d.get("registered", ""))
        for col in ws1.columns:
            ws1.column_dimensions[col[0].column_letter].width = 20

        # ── ورقة العملاء ──
        ws2 = wb.create_sheet("العملاء")
        headers2 = ["الرقم", "الحالة"]
        for col, h in enumerate(headers2, 1):
            cell = ws2.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1a4a7a")
            cell.alignment = Alignment(horizontal="center")
        for row, phone in enumerate(registered_clients, 2):
            ws2.cell(row=row, column=1, value=phone)
            blocked = phone in blocked_users and time.time() < blocked_users.get(phone, 0)
            ws2.cell(row=row, column=2, value="محظور" if blocked else "نشط")
        for col in ws2.columns:
            ws2.column_dimensions[col[0].column_letter].width = 20

        # ── ورقة الطلبات ──
        ws3 = wb.create_sheet("الطلبات")
        headers3 = ["رقم الطلب", "العميل", "المدينة", "الخدمة", "الوصف", "الحالة", "المحاولات", "التاريخ"]
        for col, h in enumerate(headers3, 1):
            cell = ws3.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="7a4a1a")
            cell.alignment = Alignment(horizontal="center")
        for row, (oid, od) in enumerate(pending_orders.items(), 2):
            ws3.cell(row=row, column=1, value=oid)
            ws3.cell(row=row, column=2, value=od.get("phone", ""))
            ws3.cell(row=row, column=3, value=od.get("city", ""))
            ws3.cell(row=row, column=4, value=od.get("service", ""))
            ws3.cell(row=row, column=5, value=od.get("description", ""))
            ws3.cell(row=row, column=6, value="مكتمل" if od.get("taken") else "معلق")
            ws3.cell(row=row, column=7, value=od.get("attempts", 1))
            ws3.cell(row=row, column=8, value=od.get("created", ""))
        for col in ws3.columns:
            ws3.column_dimensions[col[0].column_letter].width = 20

        # ── ورقة سجل العمليات ──
        ws4 = wb.create_sheet("سجل العمليات")
        headers4 = ["الوقت", "نوع الحدث", "الرقم", "رقم الطلب", "التفاصيل"]
        for col, h in enumerate(headers4, 1):
            cell = ws4.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="4a1a7a")
            cell.alignment = Alignment(horizontal="center")
        for row, entry in enumerate(reversed(activity_log), 2):
            ws4.cell(row=row, column=1, value=entry.get("time", ""))
            ws4.cell(row=row, column=2, value=entry.get("type", ""))
            ws4.cell(row=row, column=3, value=entry.get("phone", ""))
            ws4.cell(row=row, column=4, value=entry.get("order_id", ""))
            ws4.cell(row=row, column=5, value=entry.get("details", ""))
        for col in ws4.columns:
            ws4.column_dimensions[col[0].column_letter].width = 22

        # حفظ في الذاكرة وإرسال
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"mudhakkira_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )

    except ImportError:
        return "openpyxl غير مثبت — شغّل: pip install openpyxl", 500
    except Exception as e:
        return f"خطأ: {e}", 500


@app.route("/broadcast", methods=["POST"])
def broadcast_api():
    """إرسال رسالة جماعية لمقدمي الخدمة عبر API"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400

    key = data.get("key", "")
    if key != EXPORT_SECRET:
        return jsonify({"error": "غير مصرح"}), 403

    message  = data.get("message", "").strip()
    city     = data.get("city", "")
    service  = data.get("service", "")
    delay    = float(data.get("delay", 3))

    if not message:
        return jsonify({"error": "الرسالة فارغة"}), 400

    # تحديد المستهدفين
    targets = []
    for p, d in registered_providers.items():
        if d.get("status") != "active":
            continue
        if city and d.get("city") != city:
            continue
        if service and d.get("specialty") != service:
            continue
        targets.append(p)

    if not targets:
        return jsonify({"error": "لا يوجد مقدمون مطابقون", "count": 0}), 404

    # إرسال في الخلفية
    def do_broadcast():
        sent = 0
        failed = 0
        for p in targets:
            result = send_msg(p, message)
            if result:
                sent += 1
            else:
                failed += 1
            time.sleep(delay)
        log_event("بث_خارجي", "api", f"أُرسل: {sent} | فشل: {failed} | المدينة: {city or 'الكل'} | الخدمة: {service or 'الكل'}")
        # إشعار الأدمن عند الانتهاء
        send_group(ADMIN_GROUP,
            f"✅ انتهى الإرسال الجماعي\n"
            f"المُرسَل: {sent}\n"
            f"الفاشل: {failed}\n"
            f"المدينة: {city or 'الكل'}\n"
            f"الخدمة: {service or 'الكل'}"
        )

    t = threading.Thread(target=do_broadcast)
    t.daemon = True
    t.start()

    eta_min = int(len(targets) * delay / 60)
    return jsonify({
        "status": "بدأ الإرسال",
        "count": len(targets),
        "delay_seconds": delay,
        "eta_minutes": eta_min,
        "city": city or "الكل",
        "service": service or "الكل"
    }), 200


@app.route("/broadcast/status", methods=["GET"])
def broadcast_status():
    """عرض آخر عملية بث"""
    key = request.args.get("key", "")
    if key != EXPORT_SECRET:
        return jsonify({"error": "غير مصرح"}), 403

    last = None
    for entry in reversed(activity_log):
        if entry.get("type") == "بث_خارجي":
            last = entry
            break

    return jsonify({
        "providers_total": len(registered_providers),
        "providers_active": sum(1 for d in registered_providers.values() if d.get("status") == "active"),
        "last_broadcast": last
    }), 200


@app.route("/", methods=["GET"])
def home():
    return "مذكرة سلمان - البوت شغال! ✅", 200


# تحميل البيانات عند البدء
load_data()
print(f"🚀 البوت يعمل — Instance: {INSTANCE_ID}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
