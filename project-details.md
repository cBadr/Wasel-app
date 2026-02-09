# توثيق مشروع نظام الاتصال الآلي (Auto Dialer)

## 1. مقدمة
نظام **واصل (Wasel)** هو تطبيق ويب متكامل لإدارة حملات الاتصال الآلي (Auto Dialer) مصمم للعمل مع أنظمة Asterisk/Issabel. يتيح النظام إنشاء حملات اتصال، إدارة جهات الاتصال، مراقبة الحالات الحية للخطوط (Trunks/Dongles)، وتوفير تقارير مفصلة، مع نظام صلاحيات وأدوار متقدم.

---

## 2. الهيكلية العامة للنظام (Architecture)

يعتمد النظام على التقنيات التالية:
*   **Backend**: لغة Python مع إطار عمل **Flask**.
*   **Database**:
    *   **SQLite**: لتخزين بيانات التطبيق (المستخدمين، الحملات، الإعدادات).
    *   **MySQL**: للاتصال بقاعدة بيانات Asterisk CDR لجلب سجلات المكالمات.
*   **Frontend**: HTML5, Bootstrap 5, JavaScript (Chart.js للرسوم البيانية).
*   **AMI (Asterisk Manager Interface)**: للتواصل اللحظي مع سيرفر الاتصال (مراقبة الخطوط، إجراء المكالمات).
*   **Threading**: يستخدم `ThreadPoolExecutor` لإجراء المكالمات بشكل متوازي (Multi-threaded) لزيادة الكفاءة.

---

## 3. هيكل الملفات والمجلدات

```text
/
├── app.py                  # ملف التطبيق الرئيسي (Flask Routes & Views)
├── dialer_daemon.py        # المحرك الخلفي (Daemon) المسؤول عن إجراء الاتصالات
├── models.py               # نماذج قاعدة البيانات (SQLAlchemy Models)
├── ami_client.py           # كلاس للتعامل مع AMI (Asterisk Manager Interface)
├── notifications.py        # نظام الإشعارات (Telegram وغيرها)
├── requirements.txt        # المكتبات المطلوبة
├── backup_script.py        # سكريبت النسخ الاحتياطي
├── instance/
│   └── autodialer.db       # قاعدة بيانات التطبيق (SQLite)
├── static/                 # الملفات الثابتة (CSS, JS, Images)
└── templates/              # قوالب HTML (Jinja2)
    ├── base.html           # القالب الأساسي (Layout)
    ├── index.html          # الصفحة الرئيسية (Dashboard)
    ├── campaigns.html      # إدارة الحملات
    ├── contacts.html       # إدارة جهات الاتصال
    ├── monitor.html        # شاشة المراقبة الحية
    ├── packages.html       # صفحة الباقات والعروض
    ├── settings.html       # الإعدادات
    ├── users.html          # إدارة المستخدمين
    ├── roles.html          # إدارة الأدوار والصلاحيات
    └── ...
```

---

## 4. شرح المكونات الرئيسية

### 4.1. إدارة المستخدمين والصلاحيات (RBAC)
يحتوي النظام على نظام صلاحيات مرن يعتمد على **الأدوار (Roles)**.
*   **المودل**: `User` و `Role` في ملف `models.py`.
*   **الآلية**: كل دور يحتوي على مصفوفة صلاحيات (JSON) تحدد مستوى الوصول (`view`, `edit`, `none`) لكل مورد (مثل `campaigns`, `database`, `monitor`).
*   **التحقق**: يتم استخدام المزيّن `@requires_permission` في `app.py` لحماية الروابط.

### 4.2. محرك الاتصال (`dialer_daemon.py`)
هذا هو "قلب" النظام، ويعمل كعملية منفصلة أو خيط (Thread) في الخلفية.
*   يقوم بفحص الحملات النشطة (`active`) بشكل دوري.
*   يستخدم `ThreadPoolExecutor` لتوزيع المكالمات على قنوات الاتصال المتاحة (`concurrent_channels`).
*   يقوم بتحديث حالة الاتصال (`pending` -> `dialing` -> `dialed`).
*   يقوم بمزامنة نتائج المكالمات (مدة المكالمة، حالة الرد) من قاعدة بيانات Asterisk CDR عبر دالة `sync_cdr_data`.

### 4.3. واجهة المراقبة (`monitor.html` & `ami_client.py`)
*   تستخدم `SimpleAMI` للاتصال بمنفذ AMI الخاص بـ Asterisk (افتراضياً 5038).
*   تعرض حالة الطوابير (Queues)، الترانكات (Trunks)، والدونجلات (Dongles) بشكل لحظي.
*   تدعم ميزات التجسس (ChanSpy) مثل الاستماع (Listen) والهمس (Whisper).

---

## 5. أمثلة على طريقة التعديل (How-to Guide)

### مثال 1: إضافة صفحة جديدة (Route)
لإضافة صفحة جديدة، مثلاً "صفحة المساعدة"، اتبع الخطوات التالية:

1.  **إنشاء القالب**: أنشئ ملف `templates/help.html`:
    ```html
    {% extends "base.html" %}
    {% block content %}
    <h1>مركز المساعدة</h1>
    <p>مرحباً بك في صفحة المساعدة...</p>
    {% endblock %}
    ```

2.  **إضافة المسار في `app.py`**:
    ```python
    @app.route('/help')
    @login_required
    def help_page():
        return render_template('help.html')
    ```

3.  **إضافة الرابط في القائمة الجانبية (`templates/base.html`)**:
    ```html
    <li>
        <a href="{{ url_for('help_page') }}">
            <i class="fas fa-question-circle"></i> المساعدة
        </a>
    </li>
    ```

### مثال 2: تعديل قاعدة البيانات (إضافة حقل جديد)
لنفترض أنك تريد إضافة حقل "المدينة" (`city`) لجدول العملاء `Client`.

1.  **تعديل `models.py`**:
    ```python
    class Client(db.Model):
        # ... الحقول الموجودة ...
        city = db.Column(db.String(50), nullable=True) # الحقل الجديد
    ```

2.  **تحديث قاعدة البيانات**:
    بما أننا نستخدم SQLite ولا يوجد نظام Migration تلقائي (مثل Alembic) مفعّل بشكل كامل، يمكنك استخدام سكريبت بايثون بسيط لإضافة العمود:
    ```python
    import sqlite3
    conn = sqlite3.connect('instance/autodialer.db')
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE client ADD COLUMN city VARCHAR(50)")
    conn.commit()
    conn.close()
    ```

### مثال 3: تعديل منطق الاتصال (Dialing Logic)
لتغيير وقت الانتظار بين المحاولات أو منطق إعادة المحاولة، توجه إلى `dialer_daemon.py`.
*   ابحث عن الحلقة الرئيسية `while True:` أو دالة `process_campaign`.
*   لتغيير وقت الانتظار بين الدورات، عدّل `time.sleep(10)` في نهاية الملف.
*   لتعديل شرط اختيار الأرقام، عدّل استعلام `contacts` في دالة `process_campaign`.

### مثال 4: تخصيص الألوان والثيم
لتغيير ألوان النظام، عدّل ملف `static/css/style.css` أو استخدم كلاسات Bootstrap في ملفات الـ HTML مباشرة.
*   مثال: لتغيير لون القائمة الجانبية، ابحث عن `.sidebar` في ملف CSS وغيّر `background-color`.

---

## 6. ملاحظات هامة للنشر (Deployment)
*   **Vercel**: عند النشر على Vercel، تأكد من توافق المكتبات (كما واجهنا في `numpy`). استخدم `numpy<2.0.0` في `requirements.txt`.
*   **قاعدة البيانات**: SQLite تعمل جيداً للتطبيقات الصغيرة والمتوسطة. في حال الضغط العالي، يفضل الانتقال إلى MySQL/PostgreSQL بتغيير `SQLALCHEMY_DATABASE_URI` في `app.py`.
*   **الأمان**: تأكد دائماً من تغيير `SECRET_KEY` في `app.py` عند النشر الفعلي.

