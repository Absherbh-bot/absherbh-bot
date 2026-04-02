import os
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

INSTANCE_ID = os.environ.get("INSTANCE_ID", "7107565478")
API_TOKEN = os.environ.get("API_TOKEN", "503485c7be7c41aa9ae7737ea65750bd7b2e1fd0d8f943d796")
BASE_URL = f"https://7107.api.greenapi.com/waInstance{INSTANCE_ID}"

ADMIN_GROUPS = {
    "حائل": "120363405560388421@g.us",
}

# قروب التحكم الشخصي
CONTROL_GROUP = "120363426480822638@g.us"

# جلسات قروب التحكم
control_sessions = {}

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
}

CITIES = {
    "1": "حائل",
}

SERVICES = [
    "الهندسية", "العقارية", "مقاولين", "الطلابية",
    "المحامين", "مناديب توصيل", "صهريج مياه", "اسطوانات غاز",
    "سطحات", "تبريد وتكييف", "ورش وتشاليح", "شاليهات",
]

BANK_ACCOUNT = "SA2880000595608016106214"
ADMIN_PHONE = "966554325282"

user_sessions = {}
order_counter = [1000]
pending_orders = {}
blocked_users = {}
registered_clients = set()
registered_providers = {}
provider_sessions = {}


# ==========================================
# دوال الإرسال
# ==========================================
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


# ==========================================
# نظام الحظر المؤقت
# ==========================================
def is_blocked(phone):
    if phone in blocked_users:
        until = blocked_users[phone]["until"]
        remaining = int((until - time.time()) / 60)
        if time.time() < until:
            return True, remaining
        else:
            del blocked_users[phone]
    return False, 0


# ==========================================
# رسائل القوائم
# ==========================================
def send_city_menu(phone):
    send_message(phone,
        "اهلا بك في مذكرة سلمان\n\n"
        "اختر مدينتك:\n\n"
        "1 - حائل ✅\n\n"
        "(باقي المدن قريباً 🔜)\n\n"
        "ارسل رقم مدينتك"
    )


def send_service_menu(phone, city):
    send_message(phone,
        f"اخترت {city}\n\n"
        "اختر الخدمة المطلوبة:\n\n"
        "1 - الهندسية\n"
        "2 - العقارية\n"
        "3 - مقاولين\n"
        "4 - الطلابية\n"
        "5 - المحامين\n"
        "6 - مناديب توصيل\n"
        "7 - صهريج مياه\n"
        "8 - اسطوانات غاز\n"
        "9 - سطحات\n"
        "10 - تبريد وتكييف\n"
        "11 - ورش وتشاليح\n"
        "12 - شاليهات\n"
        "13 - الإدارة\n\n"
        "ارسل رقم الخدمة"
    )


def send_client_terms(phone):
    send_message(phone,
        "قبل المتابعة يرجى قراءة الشروط والموافقة عليها:\n\n"
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
        "هل توافق على الشروط؟\n\n"
        "1 - أوافق ✅\n"
        "2 - لا أوافق ❌"
    )


def send_provider_terms(phone):
    send_message(phone,
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
        "قابل للتغيير مع إشعار مسبق 7 أيام\n\n"
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
        "للتسجيل وبدء استقبال الطلبات:\n\n"
        "1 - أوافق وأريد التسجيل ✅\n"
        "2 - لا أوافق ❌\n"
        "━━━━━━━━━━━━━━"
    )


def send_admin_menu(phone):
    send_message(phone,
        "اختر من القائمة:\n\n"
        "1 - تسجيل كمقدم خدمة\n"
        "2 - تواصل مع الإدارة\n"
        "3 - شكوى"
    )


# ==========================================
# معالجة مقدم الخدمة
# ==========================================
def handle_provider_registration(phone, msg):
    session = provider_sessions.get(phone, {})
    step = session.get("step", "")

    if step == "awaiting_terms":
        if msg == "1":
            provider_sessions[phone] = {"step": "awaiting_name"}
            send_message(phone, "ممتاز! 👍\n\nأرسل اسمك الكامل كما في الهوية:")
        elif msg == "2":
            send_message(phone,
                "شكراً لاهتمامك\n"
                "نتمنى انضمامك مستقبلاً\n"
                "مذكرة سلمان 🌟"
            )
            if phone in provider_sessions:
                del provider_sessions[phone]

    elif step == "awaiting_name":
        provider_sessions[phone] = {"step": "awaiting_city", "name": msg}
        send_message(phone, f"ممتاز {msg}! 👍\n\nأرسل مدينتك:")

    elif step == "awaiting_city":
        provider_sessions[phone].update({"step": "awaiting_specialty", "city": msg})
        send_message(phone,
            "اختر تخصصك:\n\n"
            "1 - الهندسية\n"
            "2 - العقارية\n"
            "3 - مقاولين\n"
            "4 - الطلابية\n"
            "5 - المحامين\n"
            "6 - مناديب توصيل\n"
            "7 - صهريج مياه\n"
            "8 - اسطوانات غاز\n"
            "9 - سطحات\n"
            "10 - تبريد وتكييف\n"
            "11 - ورش وتشاليح\n"
            "12 - شاليهات\n\n"
            "ارسل رقم تخصصك"
        )

    elif step == "awaiting_specialty":
        services_map = {
            "1": "الهندسية", "2": "العقارية", "3": "مقاولين",
            "4": "الطلابية", "5": "المحامين", "6": "مناديب توصيل",
            "7": "صهريج مياه", "8": "اسطوانات غاز", "9": "سطحات",
            "10": "تبريد وتكييف", "11": "ورش وتشاليح", "12": "شاليهات",
        }
        if msg in services_map:
            specialty = services_map[msg]
            provider_sessions[phone].update({"step": "awaiting_payment", "specialty": specialty})
            send_message(phone,
                f"ممتاز! 🎉\n\n"
                f"الاسم: {provider_sessions[phone]['name']}\n"
                f"المدينة: {provider_sessions[phone]['city']}\n"
                f"التخصص: {specialty}\n\n"
                f"لإتمام تسجيلك:\n"
                f"حوّل 20 ريال على حساب مصرف الراجحي:\n"
                f"{BANK_ACCOUNT}\n\n"
                f"وأرسل صورة الإيصال هنا\n"
                f"سيتم تفعيل حسابك فوراً ✅"
            )
        else:
            send_message(phone, "الرجاء ارسال رقم من 1 الى 12")

    elif step == "awaiting_payment":
        send_message(phone,
            "تم استلام طلبك ✅\n"
            "سيتم مراجعة الإيصال\n"
            "وتفعيل حسابك قريباً 🕐"
        )
        admin_gid = ADMIN_GROUPS.get("حائل", "")
        if admin_gid:
            name = provider_sessions[phone].get("name", "")
            city = provider_sessions[phone].get("city", "")
            specialty = provider_sessions[phone].get("specialty", "")
            send_group_message(admin_gid,
                f"💰 طلب تسجيل مقدم خدمة جديد\n"
                f"━━━━━━━━━━━━━━\n"
                f"الاسم: {name}\n"
                f"المدينة: {city}\n"
                f"التخصص: {specialty}\n"
                f"الرقم: {phone}\n"
                f"━━━━━━━━━━━━━━\n"
                f"يرجى مراجعة الإيصال والتأكيد"
            )


# ==========================================
# معالجة رسائل العميل
# ==========================================
def handle_customer_message(phone, message_text):
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

    # الخطوة 1: اختيار المدينة
    if step == "start":
        send_city_menu(phone)
        user_sessions[phone] = {"step": "choose_city"}

    # الخطوة 2: اختيار المدينة
    elif step == "choose_city":
        if msg in CITIES:
            city = CITIES[msg]
            user_sessions[phone] = {"step": "choose_service", "city": city}
            send_service_menu(phone, city)
        else:
            send_message(phone, "الرجاء ارسال رقم صحيح\nاختر مدينتك:\n1 - حائل ✅")

    # الخطوة 3: اختيار الخدمة
    elif step == "choose_service":
        city = session.get("city")

        # الإدارة
        if msg == "13":
            user_sessions[phone] = {"step": "admin_menu", "city": city}
            send_admin_menu(phone)

        # خدمة عادية
        elif msg in [str(i) for i in range(1, 13)]:
            service = SERVICES[int(msg) - 1]
            user_sessions[phone] = {"step": "client_terms", "city": city, "service": service}

            # عميل جديد ← شروط وأحكام
            if phone not in registered_clients:
                send_client_terms(phone)
            else:
                # عميل قديم ← مباشرة للطلب
                _create_order(phone, city, service)
        else:
            send_message(phone, "الرجاء ارسال رقم من 1 الى 13")

    # الخطوة 4: شروط العميل
    elif step == "client_terms":
        city = session.get("city")
        service = session.get("service")
        if msg == "1":
            registered_clients.add(phone)
            _create_order(phone, city, service)
        elif msg == "2":
            send_message(phone, "شكراً لك\nنتمنى خدمتك في وقت آخر 🌟")
            user_sessions[phone] = {"step": "start"}
        else:
            send_client_terms(phone)

    # الخطوة 5: قائمة الإدارة
    elif step == "admin_menu":
        if msg == "1":
            # تسجيل مقدم خدمة
            provider_sessions[phone] = {"step": "awaiting_terms"}
            send_provider_terms(phone)
            user_sessions[phone] = {"step": "start"}
        elif msg == "2":
            send_message(phone,
                "سيتواصل معك فريق الإدارة قريباً\n"
                "للتواصل المباشر: " + ADMIN_PHONE
            )
            user_sessions[phone] = {"step": "start"}
        elif msg == "3":
            user_sessions[phone] = {"step": "complaint"}
            send_message(phone, "اكتب شكواك وسيتم مراجعتها فوراً:")
        else:
            send_admin_menu(phone)

    # الخطوة 6: شكوى
    elif step == "complaint":
        admin_gid = ADMIN_GROUPS.get("حائل", "")
        if admin_gid:
            send_group_message(admin_gid,
                f"🚨 شكوى جديدة\n"
                f"رقم العميل: {phone}\n"
                f"الشكوى: {msg}"
            )
        send_message(phone,
            "تم استلام شكواك ✅\n"
            "سيتم التواصل معك قريباً"
        )
        user_sessions[phone] = {"step": "start"}

    # الانتظار
    elif step == "waiting":
        send_message(phone, "طلبك قيد المعالجة، سيتم التواصل معك قريباً")

    # بعد إرسال مقدم الخدمة
    elif step == "provider_sent":
        oid = session.get("order_id")
        if msg == "1":
            send_message(phone, "ممتاز! نتمنى لك تجربة رائعة مع مذكرة سلمان 🌟")
            if oid in pending_orders:
                del pending_orders[oid]
            user_sessions[phone] = {"step": "start"}
        elif msg == "2":
            if oid in pending_orders:
                attempts = pending_orders[oid].get("attempts", 1)
                if attempts >= 3:
                    blocked_users[phone] = {"until": time.time() + 15 * 60}
                    send_message(phone,
                        "عزيزي العميل\n"
                        "تم استنفاد المحاولات الثلاث\n"
                        "سيتم إيقاف طلباتك لمدة 15 دقيقة"
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
        elif msg == "3":
            oid = session.get("order_id")
            od = pending_orders.get(oid, {})
            admin_gid = ADMIN_GROUPS.get(od.get("city", "حائل"), "")
            send_message(phone,
                "عزيزي العميل\n"
                "نأسف لما تمر به\n"
                "سيتواصل معك فريق الإدارة قريباً"
            )
            if admin_gid:
                send_group_message(admin_gid,
                    f"🚨 شكوى عميل\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"رقم الطلب: {oid}\n"
                    f"رقم العميل: {phone}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"يرجى التواصل مع العميل فوراً"
                )
            user_sessions[phone] = {"step": "start"}
        else:
            send_message(phone,
                "كيف كانت تجربتك مع مقدم الخدمة؟\n\n"
                "1 - ممتاز تم الاتفاق\n"
                "2 - لم يتم الاتفاق (إعادة الطلب)\n"
                "3 - تواصل مع الإدارة"
            )

    # سبب الإعادة
    elif step == "reason_return":
        oid = session.get("order_id")
        if msg == "1":
            user_sessions[phone] = {"step": "enter_price", "order_id": oid}
            send_message(phone, "كم السعر الذي عُرض عليك؟ (اكتب المبلغ بالريال)")
        elif msg == "2":
            _resend_order(phone, oid, "لم يتجاوب مقدم الخدمة", None)
        elif msg == "3":
            user_sessions[phone] = {"step": "enter_reason", "order_id": oid}
            send_message(phone, "اكتب سبب عدم الاتفاق:")
        else:
            send_message(phone,
                "1 - السعر مرتفع\n"
                "2 - لم يتجاوب\n"
                "3 - سبب آخر"
            )

    elif step == "enter_price":
        oid = session.get("order_id")
        _resend_order(phone, oid, "السعر مرتفع", msg)

    elif step == "enter_reason":
        oid = session.get("order_id")
        _resend_order(phone, oid, msg, None)


# ==========================================
# إنشاء الطلب
# ==========================================
def _create_order(phone, city, service):
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
    send_message(phone,
        f"تم استلام طلبك ✅\n"
        f"رقم الطلب: {oid}\n\n"
        f"سيتم إرسال رقم مقدم الخدمة قريباً\n"
        f"الرجاء الانتظار"
    )
    gid = GROUP_IDS.get(city, {}).get(service, "")
    if gid:
        send_group_message(gid,
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
def _resend_order(phone, oid, reason, price):
    if oid not in pending_orders:
        return
    od = pending_orders[oid]
    od["attempts"] += 1
    od["taken"] = False
    attempts = od["attempts"]
    city = od["city"]
    service = od["service"]
    if price:
        od["last_price"] = price

    gid = GROUP_IDS.get(city, {}).get(service, "")
    if gid:
        price_line = f"آخر سعر مُقدَّم: {od.get('last_price', '')} ريال\n" if od.get("last_price") else ""
        send_group_message(gid,
            f"طلب معاد - المحاولة {attempts} من 3\n"
            f"رقم الطلب: {oid}\n"
            f"المدينة: {city}\n"
            f"الخدمة: {service}\n"
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

    attempt_warning = "\nتنبيه: هذه آخر محاولة متاحة لك" if attempts == 3 else ""
    send_message(phone,
        f"تم إعادة طلبك\n"
        f"المحاولة {attempts} من 3{attempt_warning}\n"
        f"سيتم التواصل معك قريباً"
    )
    user_sessions[phone] = {"step": "waiting", "order_id": oid}


# ==========================================
# معالجة قروب التحكم الشخصي
# ==========================================
def handle_control_group(sender, text):
    """معالجة رسائل قروب التحكم الشخصي"""
    # التحقق أن المرسل هو المشرف فقط
    if sender.replace("@c.us", "") != ADMIN_PHONE:
        return

    session = control_sessions.get("admin", {})
    step = session.get("step", "start")
    msg = text.strip()

    if step == "start" or msg == "قروبات":
        control_sessions["admin"] = {"step": "choose_group"}
        send_group_message(CONTROL_GROUP,
            "اختر القروب:\n\n"
            "1 - الهندسية\n"
            "2 - العقارية\n"
            "3 - مقاولين\n"
            "4 - الطلابية\n"
            "5 - المحامين\n"
            "6 - مناديب توصيل\n"
            "7 - صهريج مياه\n"
            "8 - اسطوانات غاز\n"
            "9 - سطحات\n"
            "10 - تبريد وتكييف\n"
            "11 - ورش وتشاليح\n"
            "12 - شاليهات\n"
            "13 - الإدارة\n"
            "14 - الجميع 📢"
        )
    elif step == "choose_group":
        groups_map = {
            "1": ("الهندسية", GROUP_IDS["حائل"]["الهندسية"]),
            "2": ("العقارية", GROUP_IDS["حائل"]["العقارية"]),
            "3": ("مقاولين", GROUP_IDS["حائل"]["مقاولين"]),
            "4": ("الطلابية", GROUP_IDS["حائل"]["الطلابية"]),
            "5": ("المحامين", GROUP_IDS["حائل"]["المحامين"]),
            "6": ("مناديب توصيل", GROUP_IDS["حائل"]["مناديب توصيل"]),
            "7": ("صهريج مياه", GROUP_IDS["حائل"]["صهريج مياه"]),
            "8": ("اسطوانات غاز", GROUP_IDS["حائل"]["اسطوانات غاز"]),
            "9": ("سطحات", GROUP_IDS["حائل"]["سطحات"]),
            "10": ("تبريد وتكييف", GROUP_IDS["حائل"]["تبريد وتكييف"]),
            "11": ("ورش وتشاليح", GROUP_IDS["حائل"]["ورش وتشاليح"]),
            "12": ("شاليهات", GROUP_IDS["حائل"]["شاليهات"]),
            "13": ("الإدارة", ADMIN_GROUPS["حائل"]),
            "14": ("الجميع 📢", "all"),
        }

        if msg in groups_map:
            name, gid = groups_map[msg]
            control_sessions["admin"] = {"step": "write_message", "group_name": name, "group_id": gid}
            send_group_message(CONTROL_GROUP, f"اخترت: {name}\n\nاكتب رسالتك:")
        else:
            send_group_message(CONTROL_GROUP, "الرجاء ارسال رقم من 1 الى 14")

    elif step == "write_message":
        group_name = session.get("group_name")
        group_id = session.get("group_id")

        if group_id == "all":
            # إرسال للجميع
            all_groups = list(GROUP_IDS["حائل"].values()) + [ADMIN_GROUPS["حائل"]]
            for gid in all_groups:
                send_group_message(gid, msg)
            send_group_message(CONTROL_GROUP, f"✅ تم إرسال رسالتك لجميع القروبات")
        else:
            send_group_message(group_id, msg)
            send_group_message(CONTROL_GROUP, f"✅ تم إرسال رسالتك لقروب {group_name}")

        control_sessions["admin"] = {"step": "start"}


# ==========================================
# معالجة ردود القروب
# ==========================================
def handle_group_reply(group_id, sender, sender_name, reaction=None):
    sender_clean = sender.replace("@c.us", "")

    # مقدم خدمة غير مسجل
    if sender_clean not in registered_providers:
        if sender_clean not in provider_sessions:
            provider_sessions[sender_clean] = {"step": "awaiting_terms"}
            send_provider_terms(sender_clean)
        return

    # مقدم خدمة مسجل غير مدفوع
    if registered_providers.get(sender_clean, {}).get("status") != "active":
        send_message(sender_clean,
            "لن تلتقط عميلك القادم\n"
            "إلا بعد إتمام الاشتراك 😉\n\n"
            f"حوّل 20 ريال على حساب الراجحي:\n"
            f"{BANK_ACCOUNT}\n\n"
            "وأرسل صورة الإيصال للبوت"
        )
        return

    # معالجة الطلب
    for oid, od in list(pending_orders.items()):
        gid = GROUP_IDS.get(od["city"], {}).get(od["service"], "")
        if gid and gid == group_id:
            if od.get("taken"):
                return
            if sender_clean in od.get("blocked_providers", []):
                return

            cp = od["phone"]
            od["blocked_providers"].append(sender_clean)
            od["taken"] = True

            send_message(cp,
                f"ابشر به\n\n"
                f"تم قبول طلبك رقم {oid}\n"
                f"المدينة: {od['city']}\n"
                f"الخدمة: {od['service']}\n\n"
                f"مقدم الخدمة: {sender_name}\n"
                f"للتواصل: {sender_clean}"
            )

            def send_rating(cp=cp):
                time.sleep(60)
                send_message(cp,
                    "كيف كانت تجربتك مع مقدم الخدمة؟\n\n"
                    "1 - ممتاز تم الاتفاق\n"
                    "2 - لم يتم الاتفاق (إعادة الطلب)\n"
                    "3 - تواصل مع الإدارة"
                )

            import threading
            threading.Thread(target=send_rating).start()
            user_sessions[cp] = {"step": "provider_sent", "order_id": oid}
            break


# ==========================================
# Webhook
# ==========================================
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

            # التفاعلات
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
                phone = sender.replace("@c.us", "")
                if "@g.us" in chat_id:
                    # قروب التحكم الشخصي
                    if chat_id == CONTROL_GROUP:
                        handle_control_group(sender, text)
                    # باقي القروبات مقفولة للرسائل
                else:
                    # فلتر الأرقام السعودية فقط
                    if not phone.startswith("966"):
                        send_message(phone,
                            "عذراً\n"
                            "هذه الخدمة متاحة\n"
                            "للأرقام السعودية فقط 🇸🇦"
                        )
                        return jsonify({"status": "ok"}), 200

                    # معالجة مقدم الخدمة أولاً
                    if phone in provider_sessions:
                        handle_provider_registration(phone, text)
                    else:
                        handle_customer_message(phone, text)

    except Exception as e:
        print(f"Error: {e}")
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "مذكرة سلمان - البوت شغال! ✅", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
