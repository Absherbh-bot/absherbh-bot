import os
import time
import json
import requests
import threading
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# تحويل الأرقام العربية للإنجليزية
# ==========================================
def normalize(text):
    arabic = '٠١٢٣٤٥٦٧٨٩'
    for i, a in enumerate(arabic):
        text = text.replace(a, str(i))
    return text.strip()

# ==========================================
# إعدادات Green API
# ==========================================
INSTANCE_ID  = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN    = os.environ.get("API_TOKEN", "503485c7be7c41aa9ae7737ea65750bd7b2e1fd0d8f943d796")
BASE_URL     = f"https://7107.api.greenapi.com/waInstance{INSTANCE_ID}"
ADMIN_PHONE  = "966554325282"
BANK_ACCOUNT = "SA2880000595608016106214"
ADMIN_GROUP  = "120363411052676048@g.us"

# ==========================================
# المدن
# ==========================================
CITIES = {
    "1":  "الرياض",
    "2":  "جدة",
    "3":  "مكة المكرمة",
    "4":  "المدينة المنورة",
    "5":  "الدمام",
    "6":  "الخبر",
    "7":  "الأحساء",
    "8":  "تبوك",
    "9":  "أبها",
    "10": "حائل",
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
    "1":  "الهندسية",
    "2":  "العقارية",
    "3":  "مقاولين",
    "4":  "الطلابية",
    "5":  "المحامين",
    "6":  "مناديب توصيل",
    "7":  "صهريج مياه",
    "8":  "اسطوانات غاز",
    "9":  "سطحات",
    "10": "تبريد وتكييف",
    "11": "ورش وتشاليح",
    "12": "شاليهات",
}

# ==========================================
# Render Disk
# ==========================================
DATA_PATH      = "/opt/render/project/data"
PROVIDERS_FILE = f"{DATA_PATH}/providers.json"
CLIENTS_FILE   = f"{DATA_PATH}/clients.json"

# ==========================================
# البيانات في الذاكرة
# ==========================================
user_sessions     = {}
provider_sessions = {}
control_sessions  = {}
registered_clients   = set()
registered_providers = {}
pending_orders    = {}
blocked_users     = {}
provider_cooldown = {}
order_counter     = [1000]
last_activity     = {}
SESSION_TIMEOUT   = 2 * 60  # دقيقتان

# ==========================================
# حفظ وتحميل البيانات
# ==========================================
def load_data():
    global registered_providers, registered_clients
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

# ==========================================
# القوائم
# ==========================================
def menu_city(phone):
    send_msg(phone,
        "اهلا بك في مذكرة سلمان 🌟\n\n"
        "اختر مدينتك:\n\n"
        "1  - الرياض\n"
        "2  - جدة\n"
        "3  - مكة المكرمة\n"
        "4  - المدينة المنورة\n"
        "5  - الدمام\n"
        "6  - الخبر\n"
        "7  - الأحساء\n"
        "8  - تبوك\n"
        "9  - أبها\n"
        "10 - حائل\n"
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
        "\n\n13 - الإدارة\n\n"
        "ارسل رقم الخدمة"
    )

def menu_admin_options(phone):
    send_msg(phone,
        "اختر من القائمة:\n\n"
        "1 - تسجيل كمقدم خدمة\n"
        "2 - تواصل مع الإدارة\n"
        "3 - شكوى"
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
        "2 - لا أوافق ❌"
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
        "━━━━━━━━━━━━━━"
    )

# ==========================================
# تسجيل مقدم الخدمة
# ==========================================
def handle_provider_registration(phone, msg):
    session = provider_sessions.get(phone, {})
    step    = session.get("step", "")

    if step == "terms":
        if msg == "1":
            provider_sessions[phone] = {"step": "name"}
            send_msg(phone, "ممتاز! 👍\n\nأرسل اسمك الكامل:")
        elif msg == "2":
            send_msg(phone, "شكراً لاهتمامك\nنتمنى انضمامك مستقبلاً 🌟")
            provider_sessions.pop(phone, None)

    elif step == "name":
        provider_sessions[phone] = {"step": "city", "name": msg}
        menu_city(phone)

    elif step == "city":
        if msg not in CITIES:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 25")
            return
        provider_sessions[phone].update({"step": "specialty", "city": CITIES[msg]})
        send_msg(phone,
            "اختر تخصصك:\n\n"
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
            "12 - شاليهات\n\n"
            "ارسل رقم تخصصك"
        )

    elif step == "specialty":
        if msg not in SERVICES:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 12")
            return
        name      = session.get("name", "")
        city      = session.get("city", "")
        specialty = SERVICES[msg]

        registered_providers[phone] = {
            "name":       name,
            "city":       city,
            "specialty":  specialty,
            "status":     "active",
            "expiry":     "",
            "registered": datetime.now().strftime("%Y-%m-%d"),
        }
        save_providers()

        send_msg(phone,
            f"تم تسجيلك بنجاح! 🎉\n\n"
            f"الاسم: {name}\n"
            f"المدينة: {city}\n"
            f"التخصص: {specialty}\n\n"
            f"ستصلك الطلبات مباشرة على رقمك\n"
            f"أرسل 1 لاستلام أي طلب ✅"
        )
        send_group(ADMIN_GROUP,
            f"✅ مقدم خدمة جديد\n"
            f"الاسم: {name}\n"
            f"المدينة: {city}\n"
            f"التخصص: {specialty}\n"
            f"الرقم: {phone}"
        )
        provider_sessions.pop(phone, None)

# ==========================================
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
            send_msg(phone, "اكتب رسالتك للإدارة:")
        else:
            menu_provider_main(phone, provider)

    elif step == "provider_account":
        user_sessions[phone] = {"step": "provider_main"}
        menu_provider_main(phone, provider)

    elif step == "provider_contact":
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
        "queue_index":      0,
        "current_provider": None,
    }

    user_sessions[phone] = {"step": "waiting", "order_id": oid}

    send_msg(phone,
        f"تم استلام طلبك ✅\n"
        f"رقم الطلب: {oid}\n\n"
        f"سيتم التواصل معك خلال 5 دقائق"
    )

    if not matched:
        send_msg(phone,
            "عذراً\n"
            "لا يوجد مقدم خدمة متاح الآن\n"
            "سيتم التواصل معك في أقرب وقت"
        )
        send_group(ADMIN_GROUP,
            f"⚠️ لا يوجد مقدم خدمة\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {city}\n"
            f"الخدمة: {service}\n"
            f"العميل: {phone}"
        )
        return

    send_to_next(oid)

def send_to_next(oid):
    """إرسال الطلب للمقدم التالي في الطابور"""
    if oid not in pending_orders:
        return
    od       = pending_orders[oid]
    providers = od.get("providers", [])
    idx      = od.get("queue_index", 0)

    while idx < len(providers):
        p = providers[idx]
        if p in od.get("blocked", []):
            idx += 1
            continue
        if p in provider_cooldown and time.time() < provider_cooldown[p]:
            idx += 1
            continue

        od["queue_index"]     = idx
        od["current_provider"] = p

        desc = f"الوصف: {od['description']}\n" if od.get("description") else ""
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

        # انتقال تلقائي بعد 5 دقائق
        threading.Timer(5 * 60, timeout_order, args=[oid, p]).start()
        return

    # لا يوجد مقدم متاح
    cp = od["phone"]
    send_msg(cp,
        "عذراً\nلم يتمكن أي مقدم خدمة من الاستجابة الآن\n"
        "سيتواصل معك فريق الإدارة قريباً"
    )
    send_group(ADMIN_GROUP,
        f"⚠️ طلب بدون مستجيب\n"
        f"رقم الطلب: {oid}\n"
        f"المدينة: {od['city']}\n"
        f"الخدمة: {od['service']}\n"
        f"العميل: {cp}"
    )

def timeout_order(oid, p_phone):
    """انتهى وقت الانتظار — انتقل للمقدم التالي"""
    if oid not in pending_orders:
        return
    od = pending_orders[oid]
    if od.get("taken") or od.get("current_provider") != p_phone:
        return
    od["blocked"].append(p_phone)
    od["queue_index"] = od.get("queue_index", 0) + 1
    send_to_next(oid)

# ==========================================
# استلام الطلب من مقدم الخدمة
# ==========================================
def handle_provider_accept(phone):
    # فحص cooldown
    if phone in provider_cooldown and time.time() < provider_cooldown[phone]:
        remaining_m = int((provider_cooldown[phone] - time.time()) / 60)
        remaining_s = int((provider_cooldown[phone] - time.time()) % 60)
        send_msg(phone,
            f"يمكنك استلام الطلب القادم بعد:\n"
            f"{remaining_m} دقيقة و{remaining_s} ثانية ⏱️"
        )
        return

    # البحث عن طلب مرسل لهذا المقدم
    for oid, od in list(pending_orders.items()):
        if od.get("taken"):
            continue
        if od.get("current_provider") != phone:
            continue

        cp = od["phone"]
        od["taken"] = True
        od["blocked"].append(phone)
        provider_cooldown[phone] = time.time() + 5 * 60

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
    od["taken"]     = False
    if od.get("current_provider"):
        od["blocked"].append(od["current_provider"])
    od["queue_index"]      = 0
    od["current_provider"] = None
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
    send_to_next(oid)

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
        menu_city(phone)
        user_sessions[phone] = {"step": "city"}

    elif step == "city":
        if msg not in CITIES:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 25")
            return
        city = CITIES[msg]
        user_sessions[phone] = {"step": "service", "city": city}
        menu_service(phone, city)

    elif step == "service":
        city = session.get("city")
        if msg == "13":
            user_sessions[phone] = {"step": "admin_menu", "city": city}
            menu_admin_options(phone)
        elif msg in SERVICES:
            service = SERVICES[msg]
            user_sessions[phone] = {"step": "description", "city": city, "service": service}
            send_msg(phone,
                f"اخترت: {service} في {city}\n\n"
                "اكتب وصفاً قصيراً عن طلبك:\n"
                "(مثال: أحتاج كهربائي لإصلاح عطل في المنزل)"
            )
        else:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 13")

    elif step == "description":
        city        = session.get("city")
        service     = session.get("service")
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
        if msg == "1":
            provider_sessions[phone] = {"step": "terms"}
            provider_terms(phone)
            user_sessions[phone] = {"step": "start"}
        elif msg == "2":
            send_msg(phone, "سيتواصل معك فريق الإدارة قريباً 🙏")
            send_group(ADMIN_GROUP, f"📞 طلب تواصل\nرقم العميل: {phone}")
            user_sessions[phone] = {"step": "start"}
        elif msg == "3":
            user_sessions[phone] = {"step": "complaint"}
            send_msg(phone, "اكتب شكواك وسيتم مراجعتها فوراً:")
        else:
            menu_admin_options(phone)

    elif step == "complaint":
        send_group(ADMIN_GROUP, f"🚨 شكوى\nرقم العميل: {phone}\nالشكوى: {msg}")
        send_msg(phone, "تم استلام شكواك ✅\nسيتم التواصل معك قريباً")
        user_sessions[phone] = {"step": "start"}

    elif step == "waiting":
        send_msg(phone, "طلبك قيد المعالجة ⏳\nسيتم التواصل معك خلال 5 دقائق")

    elif step == "provider_sent":
        oid = session.get("order_id")
        od  = pending_orders.get(oid, {})

        if msg == "1":
            send_msg(phone, "ممتاز! نتمنى لك تجربة رائعة مع مذكرة سلمان 🌟")
            pending_orders.pop(oid, None)
            user_sessions[phone] = {"step": "start"}

        elif msg == "2":
            attempts = od.get("attempts", 1)
            if attempts >= 3:
                blocked_users[phone] = time.time() + 15 * 60
                send_msg(phone, "تم استنفاد المحاولات\nحسابك موقوف 15 دقيقة ⏱️")
                pending_orders.pop(oid, None)
                user_sessions[phone] = {"step": "start"}
            else:
                user_sessions[phone] = {"step": "reason", "order_id": oid}
                send_msg(phone,
                    "ما سبب عدم الاتفاق؟\n\n"
                    "1 - السعر مرتفع\n"
                    "2 - لم يتجاوب\n"
                    "3 - سبب آخر"
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
    session = control_sessions.get("main", {"step": "start"})
    step    = session.get("step", "start")

    if msg == "تحكم" or step in ["start", ""]:
        control_sessions["main"] = {"step": "choose"}
        send_msg(phone,
            "لوحة التحكم 🎮\n\n"
            "اختر من تريد مراسلته:\n\n"
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
            "0  - إلغاء ❌"
        )
        return

    if msg == "0":
        control_sessions["main"] = {"step": "start"}
        send_msg(phone, "تم الإلغاء ✅")
        return

    if step == "choose":
        targets = []
        label   = ""

        if msg in SERVICES:
            label   = SERVICES[msg]
            targets = [p for p, d in registered_providers.items() if d.get("specialty") == label]

        elif msg == "13":
            # اختيار مدينة محددة
            control_sessions["main"] = {"step": "choose_city"}
            send_msg(phone,
                "اختر المدينة:\n\n" +
                "\n".join([f"{k} - {v}" for k, v in CITIES.items()]) +
                "\n\n0 - إلغاء"
            )
            return

        elif msg == "14":
            label   = "الجميع"
            targets = list(registered_providers.keys())

        else:
            send_msg(phone, "الرجاء ارسال رقم صحيح")
            return

        control_sessions["main"] = {"step": "write", "targets": targets, "label": label}
        send_msg(phone, f"اخترت: {label} ({len(targets)} مقدم)\n\nاكتب رسالتك:\n(0 للإلغاء)")

    elif step == "choose_city":
        if msg not in CITIES:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 25")
            return
        city    = CITIES[msg]
        targets = [p for p, d in registered_providers.items() if d.get("city") == city]
        control_sessions["main"] = {"step": "write", "targets": targets, "label": city}
        send_msg(phone, f"اخترت: {city} ({len(targets)} مقدم)\n\nاكتب رسالتك:\n(0 للإلغاء)")

    elif step == "write":
        targets = session.get("targets", [])
        label   = session.get("label", "")
        count   = 0
        for p in targets:
            send_msg(p, msg)
            count += 1
            time.sleep(0.5)
        send_msg(phone, f"✅ تم الإرسال لـ {count} مقدم في {label}")
        control_sessions["main"] = {"step": "start"}

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

        # تجاهل القروبات
        if "@g.us" in chat_id:
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

        # فلتر الأرقام السعودية
        if not phone.startswith("966"):
            send_msg(phone, "عذراً\nهذه الخدمة متاحة للأرقام السعودية فقط 🇸🇦")
            return jsonify({"status": "ok"}), 200

        # ✅ الأدمن أولاً
        if phone == ADMIN_PHONE:
            ctrl_session = control_sessions.get("main", {"step": "start"})
            ctrl_step    = ctrl_session.get("step", "start")
            if text == "تحكم" or ctrl_step not in ["start", ""]:
                handle_control(phone, text)
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
                "city", "service", "description", "terms", "waiting",
                "provider_sent", "reason", "price", "custom_reason",
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


@app.route("/", methods=["GET"])
def home():
    return "مذكرة سلمان - البوت شغال! ✅", 200


# تحميل البيانات عند البدء
load_data()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
