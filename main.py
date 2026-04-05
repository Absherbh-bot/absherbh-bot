import os
import time
import json
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

def normalize_number(text):
    """تحويل الأرقام العربية والهندية للإنجليزية"""
    arabic = '٠١٢٣٤٥٦٧٨٩'
    english = '0123456789'
    for a, e in zip(arabic, english):
        text = text.replace(a, e)
    return text.strip()

# ==========================================
# إعدادات Green API
# ==========================================
INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN = os.environ.get("API_TOKEN", "503485c7be7c41aa9ae7737ea65750bd7b2e1fd0d8f943d796")
BASE_URL = f"https://7107.api.greenapi.com/waInstance{INSTANCE_ID}"
ADMIN_PHONE = "966554325282"
BANK_ACCOUNT = "SA2880000595608016106214"

# ==========================================
# القروبات الرئيسية فقط
# ==========================================
CONTROL_GROUP = "120363425055793404@g.us"   # التحكم الرئيسي
ADMIN_GROUP   = "120363411052676048@g.us"   # الإدارة الرئيسية

# ==========================================
# المدن والخدمات
# ==========================================
CITIES = {
    "1": "حائل",
    "2": "الرياض",
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
DATA_PATH       = "/opt/render/project/data"
PROVIDERS_FILE  = f"{DATA_PATH}/providers.json"
CLIENTS_FILE    = f"{DATA_PATH}/clients.json"
ORDERS_FILE     = f"{DATA_PATH}/orders.json"

# ==========================================
# البيانات في الذاكرة
# ==========================================
user_sessions    = {}
provider_sessions = {}
control_sessions = {}
registered_clients  = set()
registered_providers = {}
pending_orders   = {}
blocked_users    = {}
provider_cooldown = {}
pending_reactions = {}  # { msg_id: order_id } لتتبع أي رسالة تخص أي طلب
order_counter    = [1000]


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
        print(f"خطأ في حفظ مقدمي الخدمة: {e}")

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
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    chat_id = f"{to}@c.us" if "@" not in to else to
    try:
        r = requests.post(url, json={"chatId": chat_id, "message": text}, timeout=10)
        result = r.json()
        return result.get("idMessage", "")
    except Exception as e:
        print(f"Send error: {e}")
        return ""

def send_group(gid, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    try:
        r = requests.post(url, json={"chatId": gid, "message": text}, timeout=10)
        result = r.json()
        return result.get("idMessage", "")
    except Exception as e:
        print(f"Group error: {e}")
        return ""


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
# القوائم
# ==========================================
def menu_city(phone):
    send_msg(phone,
        "اهلا بك في مذكرة سلمان\n\n"
        "اختر مدينتك:\n\n"
        "1 - حائل\n"
        "2 - الرياض\n\n"
        "(باقي المدن قريباً 🔜)\n\n"
        "ارسل رقم مدينتك"
    )

def menu_service(phone, city):
    send_msg(phone,
        f"اخترت {city}\n\n"
        "اختر الخدمة:\n\n"
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
        "13 - الإدارة\n\n"
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
    name     = provider.get("name", "")
    city     = provider.get("city", "")
    specialty = provider.get("specialty", "")
    expiry   = provider.get("expiry", "غير محدد")
    status   = "مفعّل ✅" if provider.get("status") == "active" else "موقوف ⚠️"

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
    step = session.get("step", "")

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
            "1 - حائل\n"
            "2 - الرياض\n\n"
            "(باقي المدن قريباً 🔜)\n\n"
            "ارسل رقم مدينتك"
        )

    elif step == "city":
        if msg not in CITIES:
            send_msg(phone, "الرجاء ارسال رقم صحيح:\n1 - حائل\n2 - الرياض")
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
        name     = session.get("name", "")
        city     = session.get("city", "")
        specialty = SERVICES[msg]

        registered_providers[phone] = {
            "name":      name,
            "city":      city,
            "specialty": specialty,
            "status":    "active",
            "expiry":    "",
            "registered": datetime.now().strftime("%Y-%m-%d"),
        }
        save_providers()

        send_msg(phone,
            f"تم تسجيلك بنجاح! 🎉\n\n"
            f"الاسم: {name}\n"
            f"المدينة: {city}\n"
            f"التخصص: {specialty}\n\n"
            f"ستصلك الطلبات مباشرة على رقمك\n"
            f"تفاعل مع الرسالة لاستلام الطلب ✅"
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
# إنشاء الطلب وإرساله للمقدمين مباشرة
# ==========================================
def create_order(phone, city, service):
    order_counter[0] += 1
    oid = f"AB-{order_counter[0]}"

    # البحث عن مقدمي الخدمة المناسبين
    matched_providers = {
        p: d for p, d in registered_providers.items()
        if d.get("city") == city
        and d.get("specialty") == service
        and d.get("status") == "active"
        and check_subscription(d)
    }

    pending_orders[oid] = {
        "phone":             phone,
        "city":              city,
        "service":           service,
        "attempts":          1,
        "blocked_providers": [],
        "taken":             False,
        "providers":         list(matched_providers.keys()),
        "msg_ids":           {},  # { provider_phone: msg_id }
    }

    user_sessions[phone] = {"step": "waiting", "order_id": oid}

    send_msg(phone,
        f"تم استلام طلبك ✅\n"
        f"رقم الطلب: {oid}\n\n"
        f"سيتم إرسال رقم مقدم الخدمة قريباً"
    )

    if not matched_providers:
        send_msg(phone,
            "عذراً\n"
            "لا يوجد مقدم خدمة متاح الآن\n"
            "سيتم التواصل معك قريباً"
        )
        send_group(ADMIN_GROUP,
            f"⚠️ لا يوجد مقدم خدمة\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {city}\n"
            f"الخدمة: {service}\n"
            f"رقم العميل: {phone}"
        )
        return

    # إرسال رسالة لكل مقدم خدمة مباشرة
    desc_line = f"الوصف: {description}\n" if description else ""
    msg_text = (
        f"طلب جديد 🔔\n"
        f"رقم الطلب: {oid}\n"
        f"المدينة: {city}\n"
        f"الخدمة: {service}\n"
        f"{desc_line}"
        f"━━━━━━━━━━━━━━\n"
        f"لاستلام الطلب أرسل: 1\n\n"
        f"To accept send: 1\n\n"
        f"آرڈر لینے کے لیے بھیجیں: 1\n"
        f"━━━━━━━━━━━━━━"
    )

    for p_phone in matched_providers:
        msg_id = send_msg(p_phone, msg_text)
        if msg_id:
            pending_orders[oid]["msg_ids"][p_phone] = msg_id
            pending_reactions[msg_id] = oid


# ==========================================
# التحقق من الاشتراك
# ==========================================
def check_subscription(provider):
    expiry = provider.get("expiry", "")
    if not expiry:
        return True  # لا يوجد اشتراك إلزامي بعد
    try:
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
        return datetime.now() < expiry_date
    except:
        return True


# ==========================================
# إعادة الطلب
# ==========================================
def resend_order(phone, oid, reason, price=None):
    if oid not in pending_orders:
        return
    od = pending_orders[oid]
    od["attempts"] += 1
    od["taken"] = False
    attempts = od["attempts"]
    if price:
        od["last_price"] = price

    city    = od["city"]
    service = od["service"]

    # البحث عن مقدمين جدد غير محظورين
    matched_providers = {
        p: d for p, d in registered_providers.items()
        if d.get("city") == city
        and d.get("specialty") == service
        and d.get("status") == "active"
        and check_subscription(d)
        and p not in od["blocked_providers"]
    }

    price_line = f"آخر سعر: {od['last_price']} ريال\n" if od.get("last_price") else ""
    msg_text = (
        f"طلب معاد - المحاولة {attempts} من 3\n"
        f"رقم الطلب: {oid}\n"
        f"المدينة: {city}\n"
        f"الخدمة: {service}\n"
        f"{price_line}"
        f"سبب الإعادة: {reason}\n"
        f"━━━━━━━━━━━━━━\n"
        f"لاستلام الطلب أرسل: 1\n\n"
        f"To accept send: 1\n\n"
        f"آرڈر لینے کے لیے بھیجیں: 1\n"
        f"━━━━━━━━━━━━━━"
    )

    for p_phone in matched_providers:
        msg_id = send_msg(p_phone, msg_text)
        if msg_id:
            pending_reactions[msg_id] = oid

    warning = "\nتنبيه: هذه آخر محاولة" if attempts == 3 else ""
    send_msg(phone,
        f"تم إعادة طلبك\n"
        f"المحاولة {attempts} من 3{warning}\n"
        f"سيتم التواصل معك قريباً"
    )
    user_sessions[phone] = {"step": "waiting", "order_id": oid}


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
            send_msg(phone, "الرجاء ارسال رقم صحيح:\n1 - حائل\n2 - الرياض")
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
                "(مثال: أحتاج سباك لإصلاح تسرب مياه في المطبخ)"
            )
        else:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 13")

    elif step == "description":
        city        = session.get("city")
        service     = session.get("service")
        description = msg
        if phone not in registered_clients:
            user_sessions[phone] = {"step": "terms", "city": city, "service": service, "description": description}
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
        send_msg(phone, "طلبك قيد المعالجة ⏳")

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
    if sender.replace("@c.us", "") != ADMIN_PHONE:
        return

    session = control_sessions.get("main", {"step": "start"})
    step    = control_sessions.get("main", {}).get("step", "start")
    msg     = text.strip()

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
            label   = "حائل - كل الخدمات"
            targets = [
                p for p, d in registered_providers.items()
                if d.get("city") == "حائل"
            ]
        elif msg == "14":
            label   = "الرياض - كل الخدمات"
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
            time.sleep(0.5)  # تأخير لتجنب SPAM

        send_group(CONTROL_GROUP, f"✅ تم الإرسال لـ {count} مقدم خدمة في {label}")
        control_sessions["main"] = {"step": "start"}


# ==========================================
# استلام الطلب من مقدم الخدمة
# ==========================================
def handle_provider_accept(phone):
    """مقدم الخدمة يرسل 1 لاستلام الطلب"""

    # فحص cooldown
    if phone in provider_cooldown:
        until = provider_cooldown[phone]
        if time.time() < until:
            remaining_m = int((until - time.time()) / 60)
            remaining_s = int((until - time.time()) % 60)
            send_msg(phone,
                f"يمكنك استقبال الطلب القادم بعد:\n"
                f"{remaining_m} دقيقة و{remaining_s} ثانية ⏱️"
            )
            return
        del provider_cooldown[phone]

    # البحث عن طلب مناسب
    provider = registered_providers.get(phone, {})
    city     = provider.get("city", "")
    specialty = provider.get("specialty", "")

    for oid, od in list(pending_orders.items()):
        if od.get("taken"):
            continue
        if phone in od.get("blocked_providers", []):
            continue
        if od.get("city") != city or od.get("service") != specialty:
            continue

        # أخذ الطلب
        cp = od["phone"]
        od["blocked_providers"].append(phone)
        od["taken"] = True
        provider_cooldown[phone] = time.time() + 10 * 60

        provider_name = provider.get("name", "مقدم الخدمة")

        # رسالة للعميل - بدون رقم مقدم الخدمة
        send_msg(cp,
            f"ابشر به\n\n"
            f"تم قبول طلبك رقم {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n\n"
            f"سيتواصل معك مقدم الخدمة قريباً 📞"
        )

        # رسالة لمقدم الخدمة - مع رقم العميل
        send_msg(phone,
            f"تم تأكيد استلامك للطلب {oid} ✅\n\n"
            f"تواصل مع العميل:\n"
            f"الرقم: {cp}\n"
            f"الوصف: {od.get('description', 'لا يوجد وصف')}"
        )

        # تقييم بعد دقيقة
        def send_rating(cp=cp):
            time.sleep(60)
            send_msg(cp,
                "كيف كانت تجربتك مع مقدم الخدمة?\n\n"
                "1 - ممتاز تم الاتفاق\n"
                "2 - لم يتم الاتفاق (إعادة الطلب)\n"
                "3 - تواصل مع الإدارة"
            )

        threading.Thread(target=send_rating).start()
        user_sessions[cp] = {"step": "provider_sent", "order_id": oid}
        return

    send_msg(phone, "لا يوجد طلب متاح في تخصصك الآن ⏳")


# ==========================================
# معالجة التفاعل من مقدم الخدمة
# ==========================================
def handle_reaction(sender, sender_name, quoted_msg_id):
    sender_clean = sender.replace("@c.us", "")

    # هل الرسالة مرتبطة بطلب؟
    if quoted_msg_id not in pending_reactions:
        return

    oid = pending_reactions[quoted_msg_id]

    if oid not in pending_orders:
        return

    od = pending_orders[oid]

    # هل الطلب مأخوذ؟
    if od.get("taken"):
        return

    # هل مقدم الخدمة محظور من هذا الطلب؟
    if sender_clean in od.get("blocked_providers", []):
        return

    # هل مقدم الخدمة مسجل؟
    if sender_clean not in registered_providers:
        if sender_clean not in provider_sessions:
            provider_sessions[sender_clean] = {"step": "terms"}
            provider_terms(sender_clean)
        return

    # فحص cooldown
    if sender_clean in provider_cooldown:
        until = provider_cooldown[sender_clean]
        if time.time() < until:
            remaining_m = int((until - time.time()) / 60)
            remaining_s = int((until - time.time()) % 60)
            send_msg(sender_clean,
                f"يمكنك استقبال الطلب القادم بعد:\n"
                f"{remaining_m} دقيقة و{remaining_s} ثانية ⏱️"
            )
            return
        del provider_cooldown[sender_clean]

    # أخذ الطلب
    cp = od["phone"]
    od["blocked_providers"].append(sender_clean)
    od["taken"] = True
    provider_cooldown[sender_clean] = time.time() + 10 * 60

    # رسالة 1: بيانات مقدم الخدمة
    send_msg(cp,
        f"ابشر به\n\n"
        f"تم قبول طلبك رقم {oid}\n"
        f"المدينة: {od['city']}\n"
        f"الخدمة: {od['service']}\n\n"
        f"مقدم الخدمة: {sender_name}\n"
        f"للتواصل: {sender_clean}"
    )

    # رسالة 2: التقييم بعد دقيقة
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

    # تنظيف الـ pending_reactions
    for mid, oid2 in list(pending_reactions.items()):
        if oid2 == oid:
            del pending_reactions[mid]


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

        # ==========================================
        # تفاعل (Reaction)
        # ==========================================
        if mt == "reactionMessage":
            quoted_id = md.get("extendedTextMessageData", {}).get("stanzaId", "")
            if quoted_id:
                handle_reaction(sender, sender_name, quoted_id)
            return jsonify({"status": "ok"}), 200

        # ==========================================
        # رسالة نصية
        # ==========================================
        if mt == "textMessage":
            text = md.get("textMessageData", {}).get("textMessage", "")
        elif mt == "extendedTextMessage":
            text = md.get("extendedTextMessageData", {}).get("text", "")
        elif mt in ["audioMessage", "pttMessage"]:
            # رسالة صوتية
            phone = sender.replace("@c.us", "")
            if not "@g.us" in chat_id:
                send_msg(phone, "عذراً 🎤\nالرجاء إرسال رسالة نصية فقط")
            return jsonify({"status": "ok"}), 200
        else:
            text = ""

        if not text:
            return jsonify({"status": "ok"}), 200

        # تحويل الأرقام العربية للإنجليزية
        text = normalize_number(text)

        # قروب التحكم
        if "@g.us" in chat_id:
            if chat_id == CONTROL_GROUP:
                handle_control(sender, text)
            return jsonify({"status": "ok"}), 200

        # رسائل خاصة
        phone = sender.replace("@c.us", "")

        if not phone.startswith("966"):
            send_msg(phone, "عذراً\nهذه الخدمة متاحة للأرقام السعودية فقط 🇸🇦")
            return jsonify({"status": "ok"}), 200

        # توجيه الرسالة
        print(f"DEBUG: phone={phone}, text={text}")

        # 1. في جلسة تسجيل مقدم خدمة
        if phone in provider_sessions:
            print(f"DEBUG: provider_session step={provider_sessions[phone].get('step')}")
            handle_provider_registration(phone, text)
            return jsonify({"status": "ok"}), 200

        # 2. تحقق من الجلسة الحالية
        session = user_sessions.get(phone, {"step": "start"})
        step = session.get("step", "start")
        print(f"DEBUG: session step={step}")

        # 3. إذا كان في خطوة عميل — أرسله لـ handle_customer مباشرة
        customer_steps = [
            "start", "city", "service", "description", "terms",
            "waiting", "provider_sent", "reason", "price",
            "custom_reason", "admin", "complaint"
        ]

        if step in customer_steps:
            handle_customer(phone, text)
            return jsonify({"status": "ok"}), 200

        # 4. مقدم خدمة مسجل — أرسل "1" لاستلام طلب
        if phone in registered_providers:
            if text.strip() == "1":
                handle_provider_accept(phone)
            else:
                user_sessions[phone] = {"step": "provider_main"}
                handle_provider_menu(phone, text, registered_providers[phone])
            return jsonify({"status": "ok"}), 200

        # 5. شخص جديد — عميل
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
