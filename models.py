from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# تهيئة قاعدة البيانات
db = SQLAlchemy()

import json

class Role(db.Model):
    """
    نموذج الأدوار والصلاحيات
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    permissions = db.Column(db.Text, default='{}') # JSON string
    users = db.relationship('User', backref='user_role', lazy=True)

    def get_permissions(self):
        try:
            return json.loads(self.permissions) if self.permissions else {}
        except:
            return {}

    def set_permissions(self, perms_dict):
        self.permissions = json.dumps(perms_dict)

class Client(db.Model):
    """
    نموذج العملاء (المشتركين في النظام)
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)          # اسم العميل
    company_name = db.Column(db.String(100), nullable=True)   # اسم الشركة
    phone = db.Column(db.String(20), nullable=False)          # رقم الهاتف
    communication_method = db.Column(db.String(20), default='whatsapp') # وسيلة التواصل المفضلة
    address = db.Column(db.String(200), nullable=True)        # العنوان
    notes = db.Column(db.Text, nullable=True)                 # ملاحظات إضافية
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # علاقة مع المستخدمين
    users = db.relationship('User', backref='client', lazy=True)

class User(UserMixin, db.Model):
    """
    نموذج المستخدمين لتسجيل الدخول
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # role string is kept for backward compatibility but we will use role_id
    role = db.Column(db.String(20), default='user') 
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=True)
    is_banned = db.Column(db.Boolean, default=False) # حالة الحظر
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=True) # العميل التابع له (للنظام متعدد المستخدمين)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def permissions(self):
        if self.role_id and self.user_role:
            return self.user_role.get_permissions()
        # Fallback for old admin users
        if self.role == 'admin':
            return {
                'campaigns': 'edit',
                'contacts': 'edit',
                'monitor': 'view', # Monitor is usually view only but let's say view
                'settings': 'edit',
                'users': 'edit',
                'roles': 'edit'
            }
        return {}
    
    def can(self, resource, action='view'):
        """
        Check if user has permission for resource.
        action: 'view' or 'edit'. 'edit' implies 'view'.
        """
        perms = self.permissions
        user_access = perms.get(resource, 'none')
        
        if user_access == 'edit':
            return True
        if user_access == 'view' and action == 'view':
            return True
            
        return False


class Settings(db.Model):
    """
    نموذج لحفظ إعدادات النظام العامة
    """
    id = db.Column(db.Integer, primary_key=True)
    ami_host = db.Column(db.String(50), default='127.0.0.1')  # عنوان خادم AMI
    ami_port = db.Column(db.Integer, default=5038)            # منفذ AMI
    ami_user = db.Column(db.String(50), default='admin')      # اسم مستخدم AMI
    ami_secret = db.Column(db.String(50), default='amp111')   # كلمة مرور AMI
    # target_queue moved to Campaign model
    dial_delay = db.Column(db.Integer, default=5)             # الفاصل الزمني بين المكالمات بالثواني
    concurrent_channels = db.Column(db.Integer, default=1)    # عدد القنوات المتوازية (Multi-threading)
    max_retries = db.Column(db.Integer, default=3)            # عدد محاولات الاتصال القصوى
    
    # إعدادات قاعدة بيانات CDR (سجلات المكالمات)
    cdr_db_host = db.Column(db.String(50), default='127.0.0.1')
    cdr_db_port = db.Column(db.Integer, default=3306)
    cdr_db_user = db.Column(db.String(50), default='root')
    cdr_db_pass = db.Column(db.String(50), default='')
    cdr_db_name = db.Column(db.String(50), default='asteriskcdrdb')
    cdr_table_name = db.Column(db.String(50), default='cdr')

    # إعدادات تنبيهات تليجرام
    telegram_bot_token = db.Column(db.String(100), nullable=True)
    telegram_chat_id = db.Column(db.String(50), nullable=True)
    telegram_notify_start_stop = db.Column(db.Boolean, default=True) # تنبيه عند بدء/إيقاف الحملة
    telegram_notify_progress = db.Column(db.Boolean, default=True)   # تنبيه دوري للتقدم
    telegram_notify_each_call = db.Column(db.Boolean, default=False) # تنبيه عند انتهاء كل مكالمة
    telegram_notify_interval = db.Column(db.Integer, default=30)     # فاصل التنبيه بالدقائق

    # قوالب رسائل تليجرام
    telegram_template_start = db.Column(db.Text, nullable=True)
    telegram_template_finish = db.Column(db.Text, nullable=True)
    telegram_template_progress = db.Column(db.Text, nullable=True)

    # إعدادات إعادة المحاولة
    retry_interval = db.Column(db.Integer, default=60)               # الفاصل الزمني لإعادة المحاولة بالثواني

    # إعدادات المراقبة
    monitor_extension = db.Column(db.String(20), default='100')      # رقم التحويلة المستخدمة للمراقبة (ChanSpy)

    # إعدادات الاتصال التجريبي
    test_call_limit = db.Column(db.Integer, default=1) # عدد مرات التجربة قبل الحظر

class Campaign(db.Model):
    """
    نموذج الحملات الإعلانية
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)          # اسم الحملة
    status = db.Column(db.String(20), default='paused')       # حالة الحملة: active, paused, completed
    target_queue = db.Column(db.String(10), default='501')    # الكيو المستهدف للتحويل (مخصص للحملة)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # حقول جديدة للملكية والإدارة
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # مالك الحملة
    is_locked = db.Column(db.Boolean, default=False) # قفل الحملة من قبل الأدمن
    
    # علاقة مع جهات الاتصال
    contacts = db.relationship('Contact', backref='campaign', lazy=True, cascade="all, delete-orphan")

class Contact(db.Model):
    """
    نموذج جهات الاتصال (الأرقام)
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)           # اسم العميل (اختياري)
    phone_number = db.Column(db.String(20), nullable=False)   # رقم الهاتف
    status = db.Column(db.String(20), default='pending')      # الحالة: pending, dialed, failed, answered, retry
    last_dialed = db.Column(db.DateTime, nullable=True)       # وقت آخر محاولة اتصال
    retries = db.Column(db.Integer, default=0)                # عدد مرات إعادة المحاولة
    duration = db.Column(db.Integer, default=0)               # مدة المكالمة بالثواني
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False)

class Blacklist(db.Model):
    """
    القائمة السوداء للأرقام المحظورة
    """
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    reason = db.Column(db.String(200), nullable=True)
    blocked_by = db.Column(db.String(50), nullable=True) # اسم المستخدم الذي قام بالحظر
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class TestCallHistory(db.Model):
    """
    سجل الاتصالات التجريبية
    """
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
