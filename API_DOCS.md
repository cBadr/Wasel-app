# API Documentation & Developer Guide

## نظرة عامة (Overview)
هذا المستند يوضح نقاط الاتصال (API Endpoints) الحالية في النظام، والتي تعتمد حالياً على **Server-Side Rendering (Flask + Jinja2)**.
تم إعداد هذا المستند تمهيداً لفصل الواجهة الأمامية (Frontend) عن الخلفية (Backend) وتحويل النظام إلى **Single Page Application (SPA)** أو تطبيق حديث.

**ملاحظة هامة للمطورين:**
حالياً، معظم الروابط تعيد `HTML` (صفحات كاملة) أو تقوم بإعادة التوجيه `Redirect`. عند تطوير الواجهة الجديدة، يجب تعديل هذه الدوال في `app.py` لتعيد بيانات `JSON` بدلاً من `render_template` أو `redirect`.

---

## 1. المصادقة (Authentication)

يعتمد النظام حالياً على **Session-based Authentication** (Flask-Login).

### تسجيل الدخول (Login)
*   **المسار:** `/login`
*   **الطريقة:** `POST`
*   **المدخلات (Form Data):**
    *   `username`: اسم المستخدم.
    *   `password`: كلمة المرور.
*   **الاستجابة الحالية:** إعادة توجيه إلى `/` (الرئيسية) أو إعادة عرض صفحة الدخول مع رسالة خطأ.
*   **التعديل المقترح للواجهة الجديدة:** إرجاع `JSON` يحتوي على `token` أو `user_info`.

### تسجيل حساب جديد (Register)
*   **المسار:** `/register`
*   **الطريقة:** `POST`
*   **المدخلات (Form Data):**
    *   `client_name`: اسم العميل/الشركة (ينشئ سجل `Client` جديد).
    *   `phone`: رقم الهاتف.
    *   `username`: اسم المستخدم.
    *   `password`: كلمة المرور.
    *   `confirm_password`: تأكيد كلمة المرور.
*   **الاستجابة الحالية:** إعادة توجيه إلى `/login`.

### تسجيل الخروج (Logout)
*   **المسار:** `/logout`
*   **الطريقة:** `GET`
*   **الاستجابة الحالية:** إنهاء الجلسة وإعادة التوجيه إلى `/login`.

---

## 2. إدارة الحملات (Campaigns Management)

### عرض الحملات
*   **المسار:** `/campaigns`
*   **الطريقة:** `GET`
*   **الاستجابة الحالية:** صفحة HTML تعرض جدول الحملات.
*   **البيانات المطلوبة (JSON):** قائمة كائنات `Campaign`.

### إنشاء حملة جديدة
*   **المسار:** `/campaigns/create`
*   **الطريقة:** `POST`
*   **المدخلات:**
    *   `name`: اسم الحملة.
    *   `target_queue`: رقم الكيو المستهدف.

### تعديل حملة
*   **المسار:** `/campaign/<int:campaign_id>/edit`
*   **الطريقة:** `POST`
*   **المدخلات:**
    *   `name`: (اختياري) الاسم الجديد.
    *   `target_queue`: (اختياري) الكيو الجديد.

### حذف حملة
*   **المسار:** `/campaign/<int:campaign_id>/delete`
*   **الطريقة:** `GET` (يفضل تحويلها لـ `DELETE` في API).

### تشغيل/إيقاف حملة (Toggle Status)
*   **المسار:** `/campaign/<int:campaign_id>/toggle`
*   **الطريقة:** `GET`
*   **الوصف:** يقوم بتبديل الحالة بين `active` و `paused`.

---

## 3. إدارة جهات الاتصال (Contacts Management)

### عرض جهات الاتصال لحملة
*   **المسار:** `/campaign/<int:campaign_id>/view`
*   **الطريقة:** `GET`
*   **الاستجابة الحالية:** جدول HTML.

### إضافة جهة اتصال فردية
*   **المسار:** `/campaign/<int:campaign_id>/add_contact`
*   **الطريقة:** `POST`
*   **المدخلات:**
    *   `phone_number`: رقم الهاتف.

### استيراد جهات اتصال (Upload)
*   **المسار:** `/campaign/<int:campaign_id>/upload`
*   **الطريقة:** `POST`
*   **المدخلات:**
    *   `file`: ملف نصي (`.txt` أو `.csv`) يحتوي الأرقام.

### تعديل جهة اتصال
*   **المسار:** `/contact/<int:contact_id>/edit`
*   **الطريقة:** `POST`
*   **المدخلات:**
    *   `phone_number`: الرقم.
    *   `status`: الحالة.
    *   `retries`: عدد المحاولات.

### حذف جهة اتصال
*   **المسار:** `/contact/<int:contact_id>/delete`
*   **الطريقة:** `GET`

### حظر جهة اتصال (Add to Blacklist)
*   **المسار:** `/contact/<int:contact_id>/block`
*   **الطريقة:** `GET`
*   **الوصف:** يضيف الرقم للقائمة السوداء ويغير حالته في الحملة.

---

## 4. التقارير والإحصائيات (Reports & Stats)

### عرض التقارير
*   **المسار:** `/reports`
*   **الطريقة:** `GET`
*   **معاملات البحث (Query Params):**
    *   `campaign_id`: تصفية حسب الحملة.
    *   `start_date`: تاريخ البداية (YYYY-MM-DD).
    *   `end_date`: تاريخ النهاية.
    *   `phone`: بحث بجزء من الهاتف.
    *   `status`: حالة الاتصال (answered, failed, ...).
    *   `min_duration`: الحد الأدنى للمدة.
    *   `max_duration`: الحد الأقصى للمدة.

### تصدير التقارير (Excel)
*   **المسار:** `/reports/export`
*   **الطريقة:** `GET`
*   **معاملات البحث:** نفس معاملات عرض التقارير.
*   **الاستجابة:** ملف Excel (`.xlsx`) للتنزيل.

---

## 5. المراقبة الحية (Real-time Monitor)

### تحديثات الوقت الحقيقي (WebSockets)
يستخدم النظام مكتبة `Flask-SocketIO`.

#### الأحداث الصادرة من السيرفر (Server -> Client):
*   `campaign_update`: تحديث حالة حملة (التقدم، الحالة).
*   `call_status`: تحديث حالة مكالمة جارية.
*   `dongle_status`: تحديث حالة الدونجلات (Channels).

#### API داخلي للتحديث (Internal webhook)
*   **المسار:** `/api/notify/update`
*   **الطريقة:** `POST` (JSON)
*   **الوصف:** يستخدمه `dialer_daemon.py` لإرسال أحداث للواجهة.

#### API حالة الدونجلات
*   **المسار:** `/api/dongles`
*   **الطريقة:** `GET`
*   **الوصف:** يعيد قائمة بحالة الدونجلات الحالية من AMI.

---

## 6. إعدادات النظام (Settings)

### تعديل الإعدادات العامة
*   **المسار:** `/settings`
*   **الطريقة:** `POST`
*   **المدخلات:** `ami_host`, `ami_port`, `dial_delay`, `concurrent_channels`, `cdr_db_*`, `monitor_extension`, etc.

### إعدادات تليجرام
*   **المسار:** `/settings/telegram`
*   **الطريقة:** `POST`
*   **المدخلات:**
    *   `telegram_bot_token`, `telegram_chat_id`.
    *   خيارات التنبيه (`notify_start_stop`, etc.).
    *   القوالب (`telegram_template_start`, `telegram_template_finish`, `telegram_template_progress`).

### اختبار تليجرام
*   **المسار:** `/test_telegram`
*   **الطريقة:** `GET`

---

## 7. إدارة المستخدمين والأدوار (Users & Roles)

### إدارة المستخدمين
*   **المسار:** `/users`
*   **إنشاء:** `/users/add` (POST)
*   **تعديل:** `/users/<id>/edit` (POST)
*   **حذف:** `/users/<id>/delete`
*   **حظر/إلغاء حظر:** `/users/<id>/toggle_ban`

### إدارة الأدوار (RBAC)
*   **المسار:** `/roles`
*   **إنشاء:** `/roles/add` (POST)
*   **تعديل:** `/roles/<id>/edit` (POST)
*   **حذف:** `/roles/<id>/delete`
*   **هيكل الصلاحيات:** JSON يحتوي على الموارد (`campaigns`, `contacts`, `database`, `packages`, `command_screen`, etc.) والمستوى (`view`, `edit`, `none`).

---

## 8. إدارة قاعدة البيانات (Database)

*   **عرض:** `/database`
*   **تصدير (Backup):** `/database/export` (تنزيل ملف .db).
*   **استيراد (Restore):** `/database/import` (POST - رفع ملف .db).
*   **استيراد محلي:** `/database/import_local` (POST - مسار ملف على السيرفر).

---

## 9. الباقات والعروض (Packages)

*   **عرض:** `/packages`
*   **الطريقة:** `GET`
*   **الاستجابة:** صفحة HTML تعرض الباقات المتاحة.

---

## 10. شاشة الأوامر (Command Screen - SSH)

تعتمد على `Socket.IO` للاتصال التفاعلي.

### Socket Events
*   `connect_ssh`: طلب الاتصال (Client -> Server).
    *   Data: `{ host, port, username, password, cols, rows }`
*   `ssh_input`: إرسال أوامر (Client -> Server).
    *   Data: `{ data: 'ls -la\n' }`
*   `ssh_output`: استقبال مخرجات الترمينال (Server -> Client).
    *   Data: `{ data: '...output...' }`
*   `resize`: تغيير حجم الترمينال.
    *   Data: `{ cols, rows }`
*   `disconnect_ssh`: قطع الاتصال.

---

## نماذج البيانات (Data Models Overview)

### Campaign
```json
{
  "id": "Integer",
  "name": "String",
  "status": "active|paused|completed",
  "target_queue": "String",
  "user_id": "Integer (FK)",
  "is_locked": "Boolean",
  "created_at": "DateTime"
}
```

### Contact
```json
{
  "id": "Integer",
  "phone_number": "String",
  "name": "String",
  "status": "pending|dialed|answered|failed|retry",
  "duration": "Integer (seconds)",
  "retries": "Integer",
  "last_dialed": "DateTime",
  "campaign_id": "Integer (FK)"
}
```

### Client
```json
{
  "id": "Integer",
  "name": "String",
  "company_name": "String",
  "phone": "String",
  "communication_method": "String",
  "address": "String",
  "notes": "Text",
  "created_at": "DateTime"
}
```

### User
```json
{
  "id": "Integer",
  "username": "String",
  "role_id": "Integer (FK)",
  "client_id": "Integer (FK)",
  "is_banned": "Boolean",
  "role": "String (Legacy)"
}
```

### Role
```json
{
  "id": "Integer",
  "name": "String",
  "permissions": "JSON String"
}
```

### Settings
```json
{
  "id": "Integer",
  "ami_host": "String",
  "ami_port": "Integer",
  "ami_user": "String",
  "dial_delay": "Integer",
  "concurrent_channels": "Integer",
  "max_retries": "Integer",
  "monitor_extension": "String",
  "telegram_bot_token": "String",
  "telegram_chat_id": "String",
  "telegram_notify_start_stop": "Boolean",
  "telegram_notify_progress": "Boolean",
  "telegram_template_start": "Text",
  "telegram_template_finish": "Text",
  "telegram_template_progress": "Text"
}
```

### Blacklist
```json
{
  "id": "Integer",
  "phone_number": "String",
  "reason": "String",
  "added_at": "DateTime"
}
```



Badr