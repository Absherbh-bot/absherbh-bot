import os
import time
import json
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# تحويل الأرقام العربية للإنجليزية
# ==========================================
def normalize_number(text):
    arabic = '٠١٢٣٤٥٦٧٨٩'
    english = '0123456789'
    for a, e in zip(arabic, english):
        text = text.replace(a, e)
    return text.strip()

# ==========================================
# إعدادات Green API
# ==========================================
INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN   = os.environ.get("API_TOKEN", "503485c7be7c41aa9ae7737ea65750bd7b2e1fd0d8f943d796")
BASE_URL    = f"https://7107.api.greenapi.com/waInstance{INSTANCE_ID}"
ADMIN_PHONE  = "966554325282"
BANK_ACCOUNT = "SA2880000595608016106214"

# ==========================================
# القروبات الرئيسية
# ==========================================
CONTROL_GROUP = "120363425055793404@g.us"
ADMIN_GROUP   = "120363411052676048@g.us"

# ==========================================
# المدن والخدمات
# ==========================================
CITIES = {
    "1": "حائل",
    "2": "الرياض",
    "3": "القصيم",
    "4": "المدينة المنورة",
    "5": "الدمام",
    "6": "جدة",
    "7": "أبها",
    "8": "تبوك",
    "9": "الطائف",
    "10": "بريدة",
}

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
# مسار Render Disk
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
provider_cooldown = {}  # { phone: until_timestamp } — 5 دقائق بين كل طلب
order_counter     = [1000]
order_queue       = []  # طابور الطلبات
last_activity     = {}  # { phone: timestamp } آخر نشاط للمستخدم
SESSION_TIMEOUT   = 2 * 60  # دقيقتان بدون نشاط = إعادة البدء


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
        print(f"خطأ في تحميل البيانات: {e}")

def save_providers():
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(registered_providers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ في حفظ المقدمين: {e}")

def save_clients():
    try:
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(registered_clients), f, ensure_ascii=False)
    except Exception as e:
        print(f"خطأ في حفظ العملاء: {e}")


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
# عدد مقدمي الخدمة لكل تخصص ومدينة
# ==========================================
def count_providers(city, service):
    return sum(
        1 for d in registered_providers.values()
        if d.get("city") == city
        and d.get("specialty") == service
        and d.get("status") == "active"
    )

def count_providers_by_service(service):
    return sum(
        1 for d in registered_providers.values()
        if d.get("specialty") == service
        and d.get("status") == "active"
    )


# ==========================================
# نظام انتهاء الجلسة
# ==========================================
def check_session_timeout(phone):
    """إذا مر دقيقتان بدون نشاط — إعادة البدء"""
    if phone in last_activity:
        if time.time() - last_activity[phone] > SESSION_TIMEOUT:
            # انتهت الجلسة — إعادة البدء
            if phone in user_sessions:
                del user_sessions[phone]
            if phone in provider_sessions:
                del provider_sessions[phone]
            last_activity[phone] = time.time()
            return True
    last_activity[phone] = time.time()
    return False


# ==========================================
# نظام الحظر
# ==========================================
def is_blocked(phone):
    if phone in blocked_users:
        until = blocked_users[phone]
        if time.time() < until:
            remaining = int((until - time.time()) / 60)
            return True, remaining
        del blocked_users[phone]
    return False, 0


# ==========================================
# فحص الاشتراك
# ==========================================
def check_subscription(provider):
    expiry = provider.get("expiry", "")
    if not expiry:
        return True
    try:
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
        return datetime.now() < expiry_date
    except:
        return True


# ==========================================
# القوائم
# ==========================================
def menu_city(phone):
    send_msg(phone,
        "اهلا بك في مذكرة سلمان\n\n"
        "اختر مدينتك:\n\n"
        "1  - حائل\n"
        "2  - الرياض\n"
        "3  - القصيم\n"
        "4  - المدينة المنورة\n"
        "5  - الدمام\n"
        "6  - جدة\n"
        "7  - أبها\n"
        "8  - تبوك\n"
        "9  - الطائف\n"
        "10 - بريدة\n\n"
        "ارسل رقم مدينتك"
    )

def menu_service(phone, city):
    # حساب عدد المقدمين لكل خدمة في المدينة المحددة
    lines = []
    for num, svc in SERVICES.items():
        count = count_providers(city, svc)
        lines.append(f"{num.rjust(2)} - {svc} ({count} مقدم)")

    send_msg(phone,
        f"اخترت {city}\n\n"
        "اختر الخدمة:\n\n" +
        "\n".join(lines) +
        "\n13 - الإدارة\n\n"
        "ارسل رقم الخدمة"
    )

def menu_admin(phone):
    send_msg(phone,
        "اختر من القائمة:\n\n"
        "1 - تسجيل كمقدم خدمة\n"
        "2 - تواصل مع الإدارة\n"
        "3 - شكوى"
    )

def menu_provider_main(phone, provider):
    name = provider.get("name", "")
    send_msg(phone,
        f"مرحباً {name} 👋\n\n"
        "اختر من القائمة:\n\n"
        "1 - طلب جديد (كعميل)\n"
        "2 - حسابي\n"
        "3 - تواصل مع الإدارة"
    )

def menu_provider_account(phone, provider):
    name      = provider.get("name", "")
    city      = provider.get("city", "")
    specialty = provider.get("specialty", "")
    expiry    = provider.get("expiry", "غير محدد")
    status    = "مفعّل ✅" if provider.get("status") == "active" else "موقوف ⚠️"
    send_msg(phone,
        f"معلومات حسابك:\n\n"
        f"الاسم: {name}\n"
        f"المدينة: {city}\n"
        f"التخصص: {specialty}\n"
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
            del provider_sessions[phone]

    elif step == "name":
        provider_sessions[phone] = {"step": "city", "name": msg}
        send_msg(phone,
            "اختر مدينتك:\n\n"
            "1  - حائل\n"
            "2  - الرياض\n"
            "3  - القصيم\n"
            "4  - المدينة المنورة\n"
            "5  - الدمام\n"
            "6  - جدة\n"
            "7  - أبها\n"
            "8  - تبوك\n"
            "9  - الطائف\n"
            "10 - بريدة\n\n"
            "ارسل رقم مدينتك"
        )

    elif step == "city":
        if msg not in CITIES:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 10")
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
        del provider_sessions[phone]


# ==========================================
# قائمة مقدم الخدمة
# ==========================================
def handle_provider_menu(phone, msg, provider):
    # فحص انتهاء الجلسة
    timed_out = check_session_timeout(phone)
    if timed_out:
        session = {"step": "provider_main"}
        user_sessions[phone] = session
    else:
        session = user_sessions.get(phone, {"step": "provider_main"})
    step = session.get("step", "provider_main")

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
        name = provider.get("name", "")
        send_group(ADMIN_GROUP,
            f"📞 رسالة من مقدم خدمة\n"
            f"الاسم: {name}\n"
            f"الرقم: {phone}\n"
            f"الرسالة: {msg}"
        )
        send_msg(phone, "تم إرسال رسالتك ✅\nسيتم التواصل معك قريباً 🙏")
        user_sessions[phone] = {"step": "provider_main"}
        menu_provider_main(phone, provider)


# ==========================================
# إنشاء الطلب
# ==========================================
def create_order(phone, city, service, description=""):
    order_counter[0] += 1
    oid = f"AB-{order_counter[0]}"

    matched_providers = [
        p for p, d in registered_providers.items()
        if d.get("city") == city
        and d.get("specialty") == service
        and d.get("status") == "active"
        and check_subscription(d)
    ]

    pending_orders[oid] = {
        "phone":             phone,
        "city":              city,
        "service":           service,
        "description":       description,
        "attempts":          1,
        "blocked_providers": [],
        "taken":             False,
        "providers":         matched_providers,
        "queue_index":       0,
    }

    user_sessions[phone] = {"step": "waiting", "order_id": oid}

    send_msg(phone,
        f"تم استلام طلبك ✅\n"
        f"رقم الطلب: {oid}\n\n"
        f"سيتم التواصل معك خلال 5 دقائق"
    )

    if not matched_providers:
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
            f"رقم العميل: {phone}"
        )
        return

    # إرسال للأول في القائمة
    send_order_to_next_provider(oid)


# ==========================================
# نظام الطابور — إرسال للمقدم التالي
# ==========================================
def send_order_to_next_provider(oid):
    if oid not in pending_orders:
        return

    od       = pending_orders[oid]
    providers = od.get("providers", [])
    idx      = od.get("queue_index", 0)

    # البحث عن مقدم غير محظور وليس عليه cooldown
    while idx < len(providers):
        p_phone = providers[idx]

        if p_phone in od.get("blocked_providers", []):
            idx += 1
            continue

        # فحص cooldown 15 دقيقة
        if p_phone in provider_cooldown:
            until = provider_cooldown[p_phone]
            if time.time() < until:
                idx += 1
                continue
            else:
                del provider_cooldown[p_phone]

        # وجدنا مقدم خدمة متاح
        od["queue_index"]     = idx
        od["current_provider"] = p_phone

        desc_line = f"الوصف: {od['description']}\n" if od.get("description") else ""
        send_msg(p_phone,
            f"طلب جديد 🔔\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n"
            f"{desc_line}"
            f"━━━━━━━━━━━━━━\n"
            f"لاستلام الطلب أرسل: 1\n\n"
            f"To accept send: 1\n\n"
            f"آرڈر لینے کے لیے بھیجیں: 1\n"
            f"━━━━━━━━━━━━━━"
        )

        # جدولة انتقال الطلب للتالي بعد 15 دقيقة
        threading.Timer(
            5 * 60,
            check_order_timeout,
            args=[oid, p_phone]
        ).start()

        return

    # لا يوجد مقدم متاح
    cp = od["phone"]
    send_msg(cp,
        "عذراً\n"
        "لم يتمكن أي مقدم خدمة من استلام طلبك الآن\n"
        "سيتم التواصل معك في أقرب وقت"
    )
    send_group(ADMIN_GROUP,
        f"⚠️ طلب بدون مستجيب\n"
        f"رقم الطلب: {oid}\n"
        f"المدينة: {od['city']}\n"
        f"الخدمة: {od['service']}\n"
        f"رقم العميل: {cp}"
    )


# ==========================================
# انتهاء وقت الانتظار — انتقال للتالي
# ==========================================
def check_order_timeout(oid, p_phone):
    if oid not in pending_orders:
        return
    od = pending_orders[oid]
    if od.get("taken"):
        return
    if od.get("current_provider") != p_phone:
        return

    # لم يستجب — انتقل للتالي
    od["blocked_providers"].append(p_phone)
    od["queue_index"] = od.get("queue_index", 0) + 1
    send_order_to_next_provider(oid)


# ==========================================
# استلام الطلب من مقدم الخدمة
# ==========================================
def handle_provider_accept(phone):
    # فحص cooldown 15 دقيقة
    if phone in provider_cooldown:
        until = provider_cooldown[phone]
        if time.time() < until:
            remaining_m = int((until - time.time()) / 60)
            remaining_s = int((until - time.time()) % 60)
            send_msg(phone,
                f"يمكنك استلام الطلب القادم بعد:\n"
                f"{remaining_m} دقيقة و{remaining_s} ثانية ⏱️"
            )
            return
        del provider_cooldown[phone]

    # البحث عن طلب مُرسل لهذا المقدم
    for oid, od in list(pending_orders.items()):
        if od.get("taken"):
            continue
        if od.get("current_provider") != phone:
            continue
        if phone in od.get("blocked_providers", []):
            continue

        # أخذ الطلب
        cp = od["phone"]
        od["taken"] = True
        od["blocked_providers"].append(phone)
        provider_cooldown[phone] = time.time() + 5 * 60

        provider_name = registered_providers.get(phone, {}).get("name", "مقدم الخدمة")

        # رسالة للعميل — مع بيانات مقدم الخدمة
        send_msg(cp,
            f"ابشر به\n\n"
            f"تم قبول طلبك رقم {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n\n"
            f"مقدم الخدمة: {provider_name}\n"
            f"للتواصل: {phone}"
        )

        # رسالة لمقدم الخدمة — تأكيد فقط
        send_msg(phone,
            f"تم تأكيد استلامك للطلب {oid} ✅\n"
            f"سيتواصل معك العميل قريباً"
        )

        # تقييم بعد دقيقة
        def send_rating(cp=cp):
            time.sleep(60)
            send_msg(cp,
                "كيف كانت تجربتك مع مقدم الخدمة؟\n\n"
                "1 - ممتاز تم الاتفاق\n"
                "2 - لم يتم الاتفاق (إعادة الطلب)\n"
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
    od["queue_index"] = 0
    od["blocked_providers"].append(od.get("current_provider", ""))
    if price:
        od["last_price"] = price

    attempts = od["attempts"]
    warning  = "\nتنبيه: هذه آخر محاولة" if attempts == 3 else ""
    send_msg(phone,
        f"تم إعادة طلبك\n"
        f"المحاولة {attempts} من 3{warning}\n"
        f"سيتم التواصل معك خلال 5 دقائق"
    )
    user_sessions[phone] = {"step": "waiting", "order_id": oid}
    send_order_to_next_provider(oid)


# ==========================================
# سيناريو العميل
# ==========================================
def handle_customer(phone, msg):
    blocked, remaining = is_blocked(phone)
    if blocked:
        send_msg(phone, f"حسابك موقوف مؤقتاً\nالمتبقي: {remaining} دقيقة")
        return

    session = user_sessions.get(phone, {"step": "start"})
    step    = session.get("step", "start")

    if step == "start":
        menu_city(phone)
        user_sessions[phone] = {"step": "city"}

    elif step == "city":
        if msg not in CITIES:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 10")
            return
        city = CITIES[msg]
        user_sessions[phone] = {"step": "service", "city": city}
        menu_service(phone, city)

    elif step == "service":
        city = session.get("city")
        if msg == "13":
            user_sessions[phone] = {"step": "admin", "city": city}
            menu_admin(phone)
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

    elif step == "admin":
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
            send_msg(phone, "اكتب شكواك:")
        else:
            menu_admin(phone)

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
            if oid in pending_orders:
                del pending_orders[oid]
            user_sessions[phone] = {"step": "start"}

        elif msg == "2":
            attempts = od.get("attempts", 1)
            if attempts >= 3:
                blocked_users[phone] = time.time() + 15 * 60
                send_msg(phone, "تم استنفاد المحاولات\nحسابك موقوف 15 دقيقة")
                if oid in pending_orders:
                    del pending_orders[oid]
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
            city = od.get("city", "")
            send_msg(phone, "نأسف لما تمر به\nسيتواصل معك فريق الإدارة قريباً 🙏")
            send_group(ADMIN_GROUP,
                f"🚨 شكوى عميل\n"
                f"رقم الطلب: {oid}\n"
                f"رقم العميل: {phone}"
            )
            user_sessions[phone] = {"step": "start"}
        else:
            send_msg(phone,
                "كيف كانت تجربتك؟\n\n"
                "1 - ممتاز تم الاتفاق\n"
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
        oid = session.get("order_id")
        resend_order(phone, oid, "السعر مرتفع", price=msg)

    elif step == "custom_reason":
        oid = session.get("order_id")
        resend_order(phone, oid, msg)


# ==========================================
# قروب التحكم
# ==========================================
def handle_control(sender, text):
    sender_phone = sender.replace("@c.us", "").replace("+", "")
    print(f"DEBUG control: sender={sender_phone}, admin={ADMIN_PHONE}, text={text}")

    if sender_phone != ADMIN_PHONE:
        print(f"DEBUG: sender {sender_phone} != admin {ADMIN_PHONE}")
        return

    session = control_sessions.get("main", {"step": "start"})
    step    = session.get("step", "start")
    msg     = text.strip()
    print(f"DEBUG control step={step}, msg={msg}")

    if step in ["start", ""]:
        control_sessions["main"] = {"step": "choose"}
        send_group(CONTROL_GROUP,
            "اختر:\n\n"
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
            "13 - حائل (كل الخدمات)\n"
            "14 - الرياض (كل الخدمات)\n"
            "15 - الجميع 📢"
        )

    elif step == "choose":
        targets = []
        label   = ""

        if msg in SERVICES:
            label   = SERVICES[msg]
            targets = [
                p for p, d in registered_providers.items()
                if d.get("specialty") == label
            ]
        elif msg == "13":
            label   = "حائل"
            targets = [
                p for p, d in registered_providers.items()
                if d.get("city") == "حائل"
            ]
        elif msg == "14":
            label   = "الرياض"
            targets = [
                p for p, d in registered_providers.items()
                if d.get("city") == "الرياض"
            ]
        elif msg == "15":
            label   = "الجميع"
            targets = list(registered_providers.keys())
        else:
            send_group(CONTROL_GROUP, "الرجاء ارسال رقم من 1 الى 15")
            return

        control_sessions["main"] = {"step": "write", "targets": targets, "label": label}
        send_group(CONTROL_GROUP, f"اخترت: {label} ({len(targets)} مقدم)\n\nاكتب رسالتك:")

    elif step == "write":
        targets = session.get("targets", [])
        label   = session.get("label", "")
        count   = 0
        for p in targets:
            send_msg(p, msg)
            count += 1
            time.sleep(0.5)
        send_group(CONTROL_GROUP, f"✅ تم الإرسال لـ {count} مقدم في {label}")
        control_sessions["main"] = {"step": "start"}


# ==========================================
# Webhook
# ==========================================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data  = request.get_json()
        if not data:
            return jsonify({"status": "ok"}), 200

        wtype       = data.get("typeWebhook", "")
        sd          = data.get("senderData", {})
        md          = data.get("messageData", {})
        sender      = sd.get("sender", "")
        sender_name = sd.get("senderName", "مقدم الخدمة")
        chat_id     = sd.get("chatId", "")
        mt          = md.get("typeMessage", "")

        if wtype != "incomingMessageReceived":
            return jsonify({"status": "ok"}), 200

        # رسالة صوتية
        if mt in ["audioMessage", "pttMessage"]:
            if "@g.us" not in chat_id:
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

        text = normalize_number(text)

        # قروب التحكم
        print(f"DEBUG webhook: chat_id={chat_id}, CONTROL_GROUP={CONTROL_GROUP}")
        print(f"DEBUG: match={chat_id == CONTROL_GROUP}")

        if "@g.us" in chat_id:
            if chat_id == CONTROL_GROUP:
                handle_control(sender, text)
            else:
                print(f"DEBUG: group mismatch - got {chat_id} expected {CONTROL_GROUP}")
            return jsonify({"status": "ok"}), 200

        # رسائل خاصة
        phone = sender.replace("@c.us", "")

        if not phone.startswith("966"):
            send_msg(phone, "عذراً\nهذه الخدمة متاحة للأرقام السعودية فقط 🇸🇦")
            return jsonify({"status": "ok"}), 200

        # 1. في جلسة تسجيل مقدم خدمة
        if phone in provider_sessions:
            handle_provider_registration(phone, text)
            return jsonify({"status": "ok"}), 200

        # 2. مقدم خدمة مسجل
        if phone in registered_providers:
            session = user_sessions.get(phone, {"step": "provider_main"})
            step    = session.get("step", "provider_main")
            customer_steps = [
                "city", "service", "description", "terms",
                "waiting", "provider_sent", "reason", "price",
                "custom_reason", "admin", "complaint"
            ]
            if step in customer_steps:
                handle_customer(phone, text)
            elif text.strip() == "1":
                handle_provider_accept(phone)
            else:
                user_sessions[phone] = {"step": "provider_main"}
                handle_provider_menu(phone, text, registered_providers[phone])
            return jsonify({"status": "ok"}), 200

        # 3. عميل عادي
        handle_customer(phone, text)

    except Exception as e:
        print(f"Webhook error: {e}")
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "مذكرة سلمان - البوت شغال! ✅", 200


# تحميل البيانات عند بدء التشغيل
load_data()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
