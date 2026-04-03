import os
import time
import requests
import threading
from flask import Flask, request, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# ==========================================
# إعدادات Green API
# ==========================================
INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN = os.environ.get("API_TOKEN", "503485c7be7c41aa9ae7737ea65750bd7b2e1fd0d8f943d796")
BASE_URL = f"https://7107.api.greenapi.com/waInstance{INSTANCE_ID}"
ADMIN_PHONE = "966554325282"
BANK_ACCOUNT = "SA2880000595608016106214"

# ==========================================
# إعدادات Supabase
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================================
# دوال Supabase
# ==========================================
def db_get_customer(phone):
    try:
        r = supabase.table("customers").select("*").eq("phone", phone).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        print(f"db_get_customer error: {e}")
        return None

def db_save_customer(phone, city=None):
    try:
        existing = db_get_customer(phone)
        if not existing:
            supabase.table("customers").insert({"phone": phone, "city": city}).execute()
        elif city and not existing.get("city"):
            supabase.table("customers").update({"city": city}).eq("phone", phone).execute()
    except Exception as e:
        print(f"db_save_customer error: {e}")

def db_get_provider(phone):
    try:
        r = supabase.table("providers").select("*").eq("phone", phone).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        print(f"db_get_provider error: {e}")
        return None

def db_save_provider(phone, name, city, category):
    try:
        existing = db_get_provider(phone)
        if existing:
            supabase.table("providers").update({
                "name": name, "city": city, "category": category, "is_active": True
            }).eq("phone", phone).execute()
        else:
            supabase.table("providers").insert({
                "phone": phone, "name": name, "city": city, "category": category
            }).execute()
    except Exception as e:
        print(f"db_save_provider error: {e}")

def db_create_order(order_code, customer_phone, city, category):
    try:
        supabase.table("orders").insert({
            "order_code": order_code,
            "customer_phone": customer_phone,
            "city": city,
            "category": category,
            "status": "pending"
        }).execute()
    except Exception as e:
        print(f"db_create_order error: {e}")

def db_update_order(order_code, provider_phone=None, status=None):
    try:
        data = {}
        if provider_phone:
            data["provider_phone"] = provider_phone
        if status:
            data["status"] = status
        if data:
            supabase.table("orders").update(data).eq("order_code", order_code).execute()
    except Exception as e:
        print(f"db_update_order error: {e}")

def db_save_review(order_code, customer_phone, rating, comment=None, is_complaint=False):
    try:
        supabase.table("reviews").insert({
            "order_code": order_code,
            "customer_phone": customer_phone,
            "rating": rating,
            "comment": comment,
            "is_complaint": is_complaint
        }).execute()
    except Exception as e:
        print(f"db_save_review error: {e}")

def db_add_strike(phone):
    try:
        provider = db_get_provider(phone)
        if provider:
            strikes = provider.get("strikes", 0) + 1
            update = {"strikes": strikes}
            if strikes >= 3:
                update["is_active"] = False
            supabase.table("providers").update(update).eq("phone", phone).execute()
            return strikes
    except Exception as e:
        print(f"db_add_strike error: {e}")
    return 0


# ==========================================
# القروبات
# ==========================================
GROUP_IDS = {
    "حائل": {
        "الهندسية":      "120363405159631964@g.us",
        "العقارية":      "120363425763534561@g.us",
        "مقاولين":       "120363407285794575@g.us",
        "الطلابية":      "120363424399506424@g.us",
        "المحامين":      "120363409061603519@g.us",
        "مناديب توصيل": "120363406702063016@g.us",
        "صهريج مياه":   "120363407942036257@g.us",
        "اسطوانات غاز": "120363407847656145@g.us",
        "سطحات":        "120363408078892832@g.us",
        "تبريد وتكييف": "120363425242250088@g.us",
        "ورش وتشاليح":  "120363407733382686@g.us",
        "شاليهات":      "120363424951353777@g.us",
    },
    "الرياض": {
        "الهندسية":      "120363426802745983@g.us",
        "العقارية":      "120363408821300676@g.us",
        "مقاولين":       "120363406962526960@g.us",
        "الطلابية":      "120363405437547068@g.us",
        "المحامين":      "120363406811495049@g.us",
        "مناديب توصيل": "120363410052292989@g.us",
        "صهريج مياه":   "120363408203889355@g.us",
        "اسطوانات غاز": "120363425114110408@g.us",
        "سطحات":        "120363424698763610@g.us",
        "تبريد وتكييف": "120363426061619174@g.us",
        "ورش وتشاليح":  "120363426360954785@g.us",
        "شاليهات":      "120363407995383602@g.us",
    },
}

ADMIN_GROUPS = {
    "حائل":   "120363405560388421@g.us",
    "الرياض": "120363425270636965@g.us",
}

CONTROL_GROUPS = {
    "120363426480822638@g.us": "حائل",
    "120363425346411953@g.us": "الرياض",
}

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
# البيانات في الذاكرة (للسرعة)
# ==========================================
user_sessions = {}
provider_sessions = {}
control_sessions = {}
registered_clients = set()
registered_providers = {}
pending_orders = {}
blocked_users = {}
order_counter = [1000]
provider_cooldown = {}


# ==========================================
# تحميل البيانات من Supabase عند البدء
# ==========================================
def load_from_db():
    """تحميل العملاء ومزودي الخدمة من Supabase إلى الذاكرة"""
    global registered_clients, registered_providers, order_counter
    try:
        # تحميل العملاء
        customers = supabase.table("customers").select("phone").execute()
        for c in customers.data:
            registered_clients.add(c["phone"])
        print(f"✅ تم تحميل {len(registered_clients)} عميل من Supabase")

        # تحميل مزودي الخدمة
        providers = supabase.table("providers").select("*").eq("is_active", True).execute()
        for p in providers.data:
            registered_providers[p["phone"]] = {
                "name": p.get("name", "مقدم خدمة"),
                "city": p.get("city", ""),
                "specialty": p.get("category", ""),
                "status": "active" if p.get("is_active") else "inactive",
            }
        print(f"✅ تم تحميل {len(registered_providers)} مزود خدمة من Supabase")

        # تحميل آخر رقم طلب
        orders = supabase.table("orders").select("order_code").execute()
        if orders.data:
            nums = []
            for o in orders.data:
                try:
                    nums.append(int(o["order_code"].replace("AB-", "")))
                except:
                    pass
            if nums:
                order_counter[0] = max(nums)
        print(f"✅ آخر رقم طلب: AB-{order_counter[0]}")

    except Exception as e:
        print(f"load_from_db error: {e}")


# ==========================================
# أرقام مقدمي الخدمة المسجلين مسبقاً
# ==========================================
PRE_REGISTERED_PROVIDERS = set([])

for _phone in PRE_REGISTERED_PROVIDERS:
    if _phone not in registered_providers:
        registered_providers[_phone] = {
            "name": "مقدم خدمة",
            "city": "",
            "specialty": "",
            "status": "active",
        }


# ==========================================
# جلب أعضاء القروبات
# ==========================================
def fetch_group_members():
    url = f"{BASE_URL}/getGroupData/{API_TOKEN}"
    for city, groups in GROUP_IDS.items():
        for service, gid in groups.items():
            try:
                r = requests.post(url, json={"groupId": gid}, timeout=10)
                data = r.json()
                participants = data.get("participants", [])
                for p in participants:
                    phone = p.get("id", "").replace("@c.us", "")
                    if phone and phone != ADMIN_PHONE:
                        if phone not in registered_providers:
                            registered_providers[phone] = {
                                "name": "مقدم خدمة",
                                "city": city,
                                "specialty": service,
                                "status": "active",
                            }
                            # حفظ في Supabase
                            db_save_provider(phone, "مقدم خدمة", city, service)
                            print(f"✅ تم تسجيل {phone} من قروب {service} - {city}")
            except Exception as e:
                print(f"خطأ في جلب أعضاء {service} - {city}: {e}")


def is_in_any_group(phone):
    url = f"{BASE_URL}/getGroupData/{API_TOKEN}"
    for city, groups in GROUP_IDS.items():
        for service, gid in groups.items():
            try:
                r = requests.post(url, json={"groupId": gid}, timeout=10)
                data = r.json()
                participants = data.get("participants", [])
                for p in participants:
                    p_phone = p.get("id", "").replace("@c.us", "")
                    if p_phone == phone:
                        if phone not in registered_providers:
                            registered_providers[phone] = {
                                "name": "مقدم خدمة",
                                "city": city,
                                "specialty": service,
                                "status": "active",
                            }
                            db_save_provider(phone, "مقدم خدمة", city, service)
                        return True
            except Exception as e:
                print(f"خطأ: {e}")
    return False


# ==========================================
# دوال الإرسال
# ==========================================
def send_msg(to, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
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


def add_to_group(phone, gid):
    url = f"{BASE_URL}/addGroupParticipant/{API_TOKEN}"
    try:
        requests.post(url, json={
            "groupId": gid,
            "participantChatId": f"{phone}@c.us"
        }, timeout=10)
        print(f"✅ أضيف {phone} للقروب {gid}")
    except Exception as e:
        print(f"❌ خطأ إضافة: {e}")


# ==========================================
# نظام الحظر
# ==========================================
def is_blocked(phone):
    if phone in blocked_users:
        until = blocked_users[phone]
        remaining = int((until - time.time()) / 60)
        if time.time() < until:
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
# سيناريو تسجيل مقدم الخدمة
# ==========================================
def handle_provider(phone, msg):
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
        name = session.get("name", "")
        city = session.get("city", "")
        specialty = SERVICES[msg]

        # تسجيل في الذاكرة
        registered_providers[phone] = {
            "name": name,
            "city": city,
            "specialty": specialty,
            "status": "active",
        }

        # ✅ حفظ في Supabase
        db_save_provider(phone, name, city, specialty)

        gid = GROUP_IDS.get(city, {}).get(specialty, "")
        if gid:
            add_to_group(phone, gid)

        send_msg(phone,
            f"تم تسجيلك بنجاح! 🎉\n\n"
            f"الاسم: {name}\n"
            f"المدينة: {city}\n"
            f"التخصص: {specialty}\n\n"
            f"تم إضافتك لقروب {specialty} في {city}\n"
            f"يمكنك الآن استقبال الطلبات ✅"
        )
        del provider_sessions[phone]


# ==========================================
# إنشاء الطلب
# ==========================================
def create_order(phone, city, service):
    order_counter[0] += 1
    oid = f"AB-{order_counter[0]}"
    pending_orders[oid] = {
        "phone": phone,
        "city": city,
        "service": service,
        "attempts": 1,
        "blocked_providers": [],
        "taken": False,
    }
    user_sessions[phone] = {"step": "waiting", "order_id": oid}

    # ✅ حفظ الطلب في Supabase
    db_create_order(oid, phone, city, service)

    send_msg(phone,
        f"تم استلام طلبك ✅\n"
        f"رقم الطلب: {oid}\n\n"
        f"سيتم إرسال رقم مقدم الخدمة قريباً"
    )

    gid = GROUP_IDS.get(city, {}).get(service, "")
    if gid:
        send_group(gid,
            f"طلب جديد\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {city}\n"
            f"الخدمة: {service}\n"
            f"━━━━━━━━━━━━━━\n"
            f"لاستلام الطلب تفاعل مع الرسالة\n"
            f"اضغط مطولاً واختر أي تفاعل\n\n"
            f"To accept, react to this message\n"
            f"Press and hold then select any reaction\n\n"
            f"آرڈر لینے کے لیے میسج پر ری ایکشن دیں\n"
            f"میسج کو دیر تک دبائیں\n"
            f"━━━━━━━━━━━━━━"
        )


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

    # ✅ تحديث الطلب في Supabase
    db_update_order(oid, status="retrying")

    gid = GROUP_IDS.get(od["city"], {}).get(od["service"], "")
    if gid:
        price_line = f"آخر سعر: {od['last_price']} ريال\n" if od.get("last_price") else ""
        send_group(gid,
            f"طلب معاد - المحاولة {attempts} من 3\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n"
            f"{price_line}"
            f"سبب الإعادة: {reason}\n"
            f"━━━━━━━━━━━━━━\n"
            f"لاستلام الطلب تفاعل مع الرسالة\n"
            f"اضغط مطولاً واختر أي تفاعل\n\n"
            f"To accept, react to this message\n\n"
            f"آرڈر لینے کے لیے میسج پر ری ایکشن دیں\n"
            f"━━━━━━━━━━━━━━\n"
            f"مقدمو الخدمة السابقون لا يحق لهم المشاركة"
        )

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
        send_msg(phone,
            f"حسابك موقوف مؤقتاً\n"
            f"المتبقي: {remaining} دقيقة"
        )
        return

    session = user_sessions.get(phone, {"step": "start"})
    step = session.get("step", "start")

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
            if phone not in registered_clients:
                user_sessions[phone] = {"step": "terms", "city": city, "service": service}
                client_terms(phone)
            else:
                create_order(phone, city, service)
        else:
            send_msg(phone, "الرجاء ارسال رقم من 1 الى 13")

    elif step == "terms":
        city = session.get("city")
        service = session.get("service")
        if msg == "1":
            registered_clients.add(phone)
            # ✅ حفظ العميل في Supabase
            db_save_customer(phone, city)
            create_order(phone, city, service)
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
            admin_gid = ADMIN_GROUPS.get(city, "")
            if admin_gid:
                send_group(admin_gid,
                    f"📞 طلب تواصل مع الإدارة\n"
                    f"رقم العميل: {phone}"
                )
            user_sessions[phone] = {"step": "start"}
        elif msg == "3":
            user_sessions[phone] = {"step": "complaint", "city": city}
            send_msg(phone, "اكتب شكواك وسيتم مراجعتها فوراً:")
        else:
            menu_admin(phone)

    elif step == "complaint":
        city = session.get("city", "حائل")
        admin_gid = ADMIN_GROUPS.get(city, "")
        if admin_gid:
            send_group(admin_gid,
                f"🚨 شكوى جديدة\n"
                f"رقم العميل: {phone}\n"
                f"الشكوى: {msg}"
            )
        # ✅ حفظ الشكوى في Supabase
        db_save_review(
            order_code=user_sessions.get(phone, {}).get("order_id", "N/A"),
            customer_phone=phone,
            rating=1,
            comment=msg,
            is_complaint=True
        )
        send_msg(phone, "تم استلام شكواك ✅\nسيتم التواصل معك قريباً")
        user_sessions[phone] = {"step": "start"}

    elif step == "waiting":
        send_msg(phone, "طلبك قيد المعالجة، سيتم التواصل معك قريباً ⏳")

    elif step == "provider_sent":
        oid = session.get("order_id")
        od = pending_orders.get(oid, {})

        if msg == "1":
            # ✅ حفظ التقييم الإيجابي في Supabase
            db_update_order(oid, status="completed")
            db_save_review(oid, phone, rating=5, comment="تم الاتفاق")
            send_msg(phone, "ممتاز! نتمنى لك تجربة رائعة مع مذكرة سلمان 🌟")
            if oid in pending_orders:
                del pending_orders[oid]
            user_sessions[phone] = {"step": "start"}

        elif msg == "2":
            attempts = od.get("attempts", 1)
            if attempts >= 3:
                blocked_users[phone] = time.time() + 15 * 60
                db_update_order(oid, status="failed")
                send_msg(phone,
                    "تم استنفاد المحاولات الثلاث\n"
                    "حسابك موقوف 15 دقيقة"
                )
                if oid in pending_orders:
                    del pending_orders[oid]
                user_sessions[phone] = {"step": "start"}
            else:
                user_sessions[phone] = {"step": "reason", "order_id": oid}
                send_msg(phone,
                    "ما سبب عدم الاتفاق؟\n\n"
                    "1 - السعر مرتفع\n"
                    "2 - لم يتجاوب مقدم الخدمة\n"
                    "3 - سبب آخر"
                )

        elif msg == "3":
            city = od.get("city", "حائل")
            admin_gid = ADMIN_GROUPS.get(city, "")
            send_msg(phone,
                "عزيزي العميل\n"
                "نأسف لما تمر به\n"
                "سيتواصل معك فريق الإدارة قريباً 🙏"
            )
            if admin_gid:
                send_group(admin_gid,
                    f"🚨 شكوى عميل\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"رقم الطلب: {oid}\n"
                    f"رقم العميل: {phone}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"يرجى التواصل مع العميل فوراً"
                )
            # ✅ حفظ الشكوى في Supabase
            db_save_review(oid, phone, rating=1, is_complaint=True)
            db_update_order(oid, status="complaint")
            user_sessions[phone] = {"step": "start"}
        else:
            send_msg(phone,
                "كيف كانت تجربتك؟\n\n"
                "1 - ممتاز تم الاتفاق\n"
                "2 - لم يتم الاتفاق (إعادة)\n"
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
            send_msg(phone,
                "1 - السعر مرتفع\n"
                "2 - لم يتجاوب\n"
                "3 - سبب آخر"
            )

    elif step == "price":
        oid = session.get("order_id")
        resend_order(phone, oid, "السعر مرتفع", price=msg)

    elif step == "custom_reason":
        oid = session.get("order_id")
        resend_order(phone, oid, msg)


# ==========================================
# سيناريو قروب التحكم
# ==========================================
def handle_control(sender, text, group_id):
    if sender.replace("@c.us", "") != ADMIN_PHONE:
        return

    city = CONTROL_GROUPS.get(group_id, "حائل")
    session = control_sessions.get(city, {"step": "start"})
    step = session.get("step", "start")
    msg = text.strip()

    if step in ["start", ""]:
        control_sessions[city] = {"step": "choose", "reply": group_id}
        send_group(group_id,
            f"اختر قروب {city}:\n\n"
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
            "13 - الإدارة\n"
            "14 - الجميع 📢"
        )

    elif step == "choose":
        reply = session.get("reply", group_id)
        city_groups = GROUP_IDS.get(city, {})
        gmap = {
            "1":  ("الهندسية",      city_groups.get("الهندسية", "")),
            "2":  ("العقارية",      city_groups.get("العقارية", "")),
            "3":  ("مقاولين",       city_groups.get("مقاولين", "")),
            "4":  ("الطلابية",      city_groups.get("الطلابية", "")),
            "5":  ("المحامين",      city_groups.get("المحامين", "")),
            "6":  ("مناديب توصيل", city_groups.get("مناديب توصيل", "")),
            "7":  ("صهريج مياه",   city_groups.get("صهريج مياه", "")),
            "8":  ("اسطوانات غاز", city_groups.get("اسطوانات غاز", "")),
            "9":  ("سطحات",        city_groups.get("سطحات", "")),
            "10": ("تبريد وتكييف", city_groups.get("تبريد وتكييف", "")),
            "11": ("ورش وتشاليح",  city_groups.get("ورش وتشاليح", "")),
            "12": ("شاليهات",      city_groups.get("شاليهات", "")),
            "13": ("الإدارة",      ADMIN_GROUPS.get(city, "")),
            "14": ("الجميع 📢",    "all"),
        }
        if msg in gmap:
            name, gid = gmap[msg]
            control_sessions[city] = {"step": "write", "name": name, "gid": gid, "reply": reply}
            send_group(reply, f"اخترت: {name}\n\nاكتب رسالتك:")
        else:
            send_group(reply, "الرجاء ارسال رقم من 1 الى 14")

    elif step == "write":
        name = session.get("name")
        gid  = session.get("gid")
        reply = session.get("reply", group_id)

        if gid == "all":
            targets = list(GROUP_IDS.get(city, {}).values())
            admin_g = ADMIN_GROUPS.get(city, "")
            if admin_g:
                targets.append(admin_g)
            for g in targets:
                send_group(g, msg)
            send_group(reply, "✅ تم الإرسال لجميع القروبات")
        else:
            send_group(gid, msg)
            send_group(reply, f"✅ تم الإرسال لقروب {name}")

        control_sessions[city] = {"step": "start"}


# ==========================================
# سيناريو القروب (تفاعل)
# ==========================================
def handle_reaction(group_id, sender, sender_name):
    sender_clean = sender.replace("@c.us", "")

    if sender_clean not in registered_providers:
        if sender_clean not in provider_sessions:
            provider_sessions[sender_clean] = {"step": "terms"}
            provider_terms(sender_clean)
        return

    if sender_clean in provider_cooldown:
        until = provider_cooldown[sender_clean]
        if time.time() < until:
            remaining = int((until - time.time()) / 60)
            remaining_sec = int((until - time.time()) % 60)
            send_msg(sender_clean,
                f"عزيزي مقدم الخدمة\n\n"
                f"يمكنك استقبال الطلب القادم بعد:\n"
                f"{remaining} دقيقة و{remaining_sec} ثانية ⏱️"
            )
            return
        else:
            del provider_cooldown[sender_clean]

    for oid, od in list(pending_orders.items()):
        gid = GROUP_IDS.get(od["city"], {}).get(od["service"], "")
        if gid != group_id:
            continue
        if od.get("taken"):
            return
        if sender_clean in od.get("blocked_providers", []):
            return

        cp = od["phone"]
        od["blocked_providers"].append(sender_clean)
        od["taken"] = True

        provider_cooldown[sender_clean] = time.time() + 10 * 60

        # ✅ تحديث الطلب بمزود الخدمة في Supabase
        db_update_order(oid, provider_phone=sender_clean, status="accepted")

        send_msg(cp,
            f"ابشر به\n\n"
            f"تم قبول طلبك رقم {oid}\n"
            f"المدينة: {od['city']}\n"
            f"الخدمة: {od['service']}\n\n"
            f"مقدم الخدمة: {sender_name}\n"
            f"للتواصل: {sender_clean}"
        )

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
        break


# ==========================================
# Webhook الرئيسي
# ==========================================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "ok"}), 200

        wtype = data.get("typeWebhook", "")
        sd = data.get("senderData", {})
        md = data.get("messageData", {})
        sender = sd.get("sender", "")
        sender_name = sd.get("senderName", "مقدم الخدمة")
        chat_id = sd.get("chatId", "")
        mt = md.get("typeMessage", "")

        if wtype != "incomingMessageReceived":
            return jsonify({"status": "ok"}), 200

        if mt == "reactionMessage":
            if "@g.us" in chat_id:
                handle_reaction(chat_id, sender, sender_name)
            return jsonify({"status": "ok"}), 200

        if mt == "textMessage":
            text = md.get("textMessageData", {}).get("textMessage", "")
        elif mt == "extendedTextMessage":
            text = md.get("extendedTextMessageData", {}).get("text", "")
        else:
            text = ""

        if not text:
            return jsonify({"status": "ok"}), 200

        if "@g.us" in chat_id:
            if chat_id in CONTROL_GROUPS:
                handle_control(sender, text, chat_id)
            return jsonify({"status": "ok"}), 200

        phone = sender.replace("@c.us", "")

        if not phone.startswith("966"):
            send_msg(phone,
                "عذراً\n"
                "هذه الخدمة متاحة للأرقام السعودية فقط 🇸🇦"
            )
            return jsonify({"status": "ok"}), 200

        if phone in provider_sessions:
            handle_provider(phone, text)
        elif phone in registered_providers:
            handle_customer(phone, text)
        elif phone in registered_clients:
            handle_customer(phone, text)
        else:
            if is_in_any_group(phone):
                handle_customer(phone, text)
            else:
                handle_customer(phone, text)

    except Exception as e:
        print(f"Webhook error: {e}")
    return jsonify({"status": "ok"}), 200


@app.route("/fetch_members", methods=["GET"])
def fetch_members():
    fetch_group_members()
    return f"تم تسجيل {len(registered_providers)} مقدم خدمة ✅", 200


@app.route("/", methods=["GET"])
def home():
    return "مذكرة سلمان - البوت شغال! ✅", 200


if __name__ == "__main__":
    # تحميل البيانات من Supabase عند البدء
    load_from_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
