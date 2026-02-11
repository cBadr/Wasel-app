import notifications
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, Campaign, Contact, Settings, User, Role, Client, Blacklist, TestCallHistory
from sqlalchemy import func
from functools import wraps
import os
import socket
import pymysql
import shutil
import paramiko
import threading
from datetime import datetime
import pandas as pd
import io
import hashlib
import time
from flask_socketio import SocketIO, emit
from ami_client import SimpleAMI

app = Flask(__name__, instance_relative_config=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
ssh_sessions = {}
# التأكد من وجود مجلد instance
try:
    os.makedirs(app.instance_path)
except OSError:
    pass

# استخدام مسار قاعدة البيانات داخل مجلد instance
# db_path = os.path.join(app.instance_path, 'autodialer.db')
# app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Medoza120a@127.0.0.1/wasel'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'issabel_secret_key_auto_dialer'

db.init_app(app)

# إعداد Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def requires_permission(resource, action='view'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            
            if not current_user.can(resource, action):
                flash('ليس لديك صلاحية للقيام بهذا الإجراء', 'danger')
                return redirect(request.referrer or url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Context Processor لإتاحة التاريخ في كل القوالب
@app.context_processor
def inject_now():
    return {'now_date': datetime.now().strftime('%Y-%m-%d')}

def check_system_status():
    status = {'ami': False, 'mysql': False}
    try:
        settings = Settings.query.first()
        if not settings:
            return status
            
        # Check AMI
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            result = s.connect_ex((settings.ami_host, settings.ami_port))
            if result == 0:
                status['ami'] = True
            s.close()
        except:
            pass
            
        # Check MySQL
        try:
            conn = pymysql.connect(
                host=settings.cdr_db_host,
                port=settings.cdr_db_port,
                user=settings.cdr_db_user,
                password=settings.cdr_db_pass,
                database=settings.cdr_db_name,
                connect_timeout=1
            )
            conn.close()
            status['mysql'] = True
        except:
            pass
    except:
        pass
        
    return status

with app.app_context():
    db.create_all()
    # إنشاء إعدادات افتراضية إذا لم تكن موجودة
    if not Settings.query.first():
        default_settings = Settings()
        db.session.add(default_settings)
        db.session.commit()
    
    # إنشاء مستخدم افتراضي (admin / admin123)
    if not User.query.filter_by(username='admin').first():
        admin_user = User(username='admin', role='admin')
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("تم إنشاء المستخدم الافتراضي: admin / admin123")

# --- تسجيل الدخول ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if user.is_banned:
                flash('تم حظر حسابك. يرجى الاتصال بالمسؤول.', 'danger')
                return redirect(url_for('login'))
                
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        # Client Data
        client_name = request.form.get('client_name')
        phone = request.form.get('phone')
        
        # User Data
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not client_name or not phone or not username or not password:
            flash('جميع الحقول مطلوبة', 'danger')
            return redirect(url_for('register'))
            
        if password != confirm_password:
            flash('كلمة المرور غير متطابقة', 'danger')
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم مسجل بالفعل', 'danger')
            return redirect(url_for('register'))
            
        # Create Client
        new_client = Client(
            name=client_name,
            phone=phone,
            company_name=client_name # Default company name to client name
        )
        db.session.add(new_client)
        db.session.flush() # To get client ID
        
        # Get 'user' role
        user_role = Role.query.filter_by(name='user').first()
        if not user_role:
             # Create default user role if it doesn't exist
             user_role = Role(name='user', permissions='{"campaigns": "view", "contacts": "view"}') 
             db.session.add(user_role)
             db.session.flush()

        # Create User
        new_user = User(
            username=username,
            role_id=user_role.id,
            client_id=new_client.id,
            role='user' # Explicitly set legacy role to user
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- الصفحة الرئيسية ---
@app.route('/')
@login_required
def index():
    # التحقق من صلاحية الأدمن
    is_admin = current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')
    
    # Base query for contacts
    contact_query = Contact.query
    
    if is_admin:
        # الأدمن يرى كل الإحصائيات
        total_campaigns = Campaign.query.count()
        active_campaigns = Campaign.query.filter_by(status='active').count()
        pending_contacts = Contact.query.filter_by(status='pending').count()
        dialed_contacts = Contact.query.filter_by(status='dialed').count()
        
        # تفاصيل إضافية للرسم البياني
        answered_contacts = Contact.query.filter_by(status='answered').count()
        busy_contacts = Contact.query.filter_by(status='failed').count() # Assuming failed includes busy/congestion
        # If we had more statuses like 'busy', 'noanswer', we would query them.
        # Currently we map CDR disposition: ANSWERED -> answered, others -> failed (after retries)
        # But 'dialed' is transient status.
        # Let's use what we have:
        # answered, failed, dialed (in progress), pending, retry
        
        failed_contacts = Contact.query.filter_by(status='failed').count()
        retry_contacts = Contact.query.filter_by(status='retry').count()
        
    else:
        # المستخدم العادي يرى إحصائيات حملاته فقط
        total_campaigns = Campaign.query.filter_by(user_id=current_user.id).count()
        active_campaigns = Campaign.query.filter_by(user_id=current_user.id, status='active').count()
        
        # للانضمام مع جدول الحملات لفلترة جهات الاتصال حسب مالك الحملة
        base_contact_join = Contact.query.join(Campaign).filter(Campaign.user_id == current_user.id)
        
        pending_contacts = base_contact_join.filter(Contact.status == 'pending').count()
        dialed_contacts = base_contact_join.filter(Contact.status == 'dialed').count()
        
        answered_contacts = base_contact_join.filter(Contact.status == 'answered').count()
        failed_contacts = base_contact_join.filter(Contact.status == 'failed').count()
        retry_contacts = base_contact_join.filter(Contact.status == 'retry').count()
        # Busy/No Answer are aggregated into 'failed' or 'retry' in current logic
    
    system_status = check_system_status()
    
    return render_template('index.html', 
                           total_campaigns=total_campaigns,
                           active_campaigns=active_campaigns,
                           pending_contacts=pending_contacts,
                           dialed_contacts=dialed_contacts,
                           answered_contacts=answered_contacts,
                           failed_contacts=failed_contacts,
                           retry_contacts=retry_contacts,
                           ami_status=system_status['ami'],
                           mysql_status=system_status['mysql'])

# --- إدارة الحملات ---
@app.route('/campaigns')
@login_required
@requires_permission('campaigns', 'view')
def campaigns():
    if current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin'):
        all_campaigns = Campaign.query.order_by(Campaign.created_at.desc()).all()
    else:
        all_campaigns = Campaign.query.filter_by(user_id=current_user.id).order_by(Campaign.created_at.desc()).all()
    return render_template('campaigns.html', campaigns=all_campaigns)

@app.route('/campaigns/create', methods=['GET', 'POST'])
@login_required
@requires_permission('campaigns', 'edit')
def create_campaign():
    if request.method == 'GET':
        return render_template('campaign_create.html')
        
    name = request.form.get('name')
    target_queue = request.form.get('target_queue')
    
    # Scheduling fields
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    daily_start_str = request.form.get('daily_start_time')
    daily_end_str = request.form.get('daily_end_time')
    
    # Advanced fields
    concurrent_channels = request.form.get('concurrent_channels')
    max_retries = request.form.get('max_retries')
    retry_interval = request.form.get('retry_interval')
    
    if name and target_queue:
        new_campaign = Campaign(name=name, target_queue=target_queue, user_id=current_user.id)
        
        # Parse dates and times
        if start_date_str:
            try:
                new_campaign.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                new_campaign.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if daily_start_str:
            try:
                new_campaign.daily_start_time = datetime.strptime(daily_start_str, '%H:%M').time()
            except ValueError:
                pass
        if daily_end_str:
            try:
                new_campaign.daily_end_time = datetime.strptime(daily_end_str, '%H:%M').time()
            except ValueError:
                pass
                
        # Parse integers
        if concurrent_channels:
            try:
                new_campaign.concurrent_channels = int(concurrent_channels)
            except ValueError:
                pass
        if max_retries:
            try:
                new_campaign.max_retries = int(max_retries)
            except ValueError:
                pass
        if retry_interval:
            try:
                new_campaign.retry_interval = int(retry_interval)
            except ValueError:
                pass
                
        db.session.add(new_campaign)
        db.session.commit()
        flash('تم إنشاء الحملة بنجاح', 'success')
        return redirect(url_for('campaigns'))
        
    flash('يرجى ملء جميع الحقول الإجبارية', 'danger')
    return render_template('campaign_create.html')

@app.route('/campaign/<int:campaign_id>/edit', methods=['POST'])
@login_required
@requires_permission('campaigns', 'edit')
def edit_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Check ownership or admin
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية تعديل هذه الحملة', 'danger')
        return redirect(url_for('campaigns'))
        
    name = request.form.get('name')
    target_queue = request.form.get('target_queue')
    
    if name:
        campaign.name = name
    if target_queue:
        campaign.target_queue = target_queue
        
    db.session.commit()
    flash('تم تحديث بيانات الحملة بنجاح', 'success')
    return redirect(url_for('campaigns'))

@app.route('/campaign/<int:campaign_id>/delete')
@login_required
@requires_permission('campaigns', 'edit')
def delete_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Check ownership or admin
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية حذف هذه الحملة', 'danger')
        return redirect(url_for('campaigns'))

    # حذف جهات الاتصال المرتبطة أولاً (رغم أن cascade قد يعالجها لكن للأمان)
    Contact.query.filter_by(campaign_id=campaign_id).delete()
    db.session.delete(campaign)
    db.session.commit()
    flash('تم حذف الحملة بنجاح', 'success')
    return redirect(url_for('campaigns'))

@app.route('/campaign/<int:campaign_id>/toggle')
@login_required
@requires_permission('campaigns', 'edit')
def toggle_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Check ownership or admin
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية تشغيل/إيقاف هذه الحملة', 'danger')
        return redirect(url_for('campaigns'))
        
    # Check if locked by admin
    if campaign.is_locked:
        is_admin = current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')
        if not is_admin:
            flash('تم إيقاف هذه الحملة من قبل المسؤول ولا يمكن تشغيلها.', 'danger')
            return redirect(url_for('campaigns'))

    config = Settings.query.first()
    
    if campaign.status == 'active':
        campaign.status = 'paused'
        flash('تم إيقاف الحملة مؤقتاً', 'warning')
    else:
        # إيقاف أي حملة أخرى نشطة (اختياري، لضمان حملة واحدة نشطة في كل مرة إذا رغبت)
        # active = Campaign.query.filter_by(status='active').first()
        # if active and active.id != campaign.id:
        #     active.status = 'paused'
        
        campaign.status = 'active'
        flash('تم تفعيل الحملة', 'success')
    
    db.session.commit()
    
    # إرسال تنبيه عبر تليجرام
    if config and config.telegram_bot_token and config.telegram_chat_id and config.telegram_notify_start_stop:
        msg = notifications.format_campaign_status_message(campaign.name, campaign.status)
        notifications.send_telegram_message(config.telegram_bot_token, config.telegram_chat_id, msg)
        
    return redirect(url_for('campaigns'))

@app.route('/contacts')
@login_required
@requires_permission('contacts', 'view')
def contacts_page():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    campaign_filter = request.args.get('campaign_id', '')
    status_filter = request.args.get('status', '')
    
    # Base query
    query = Contact.query
    
    # Filter by user permissions
    if current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        # Join with Campaign to filter by user_id
        query = query.join(Campaign).filter(Campaign.user_id == current_user.id)
    
    # Apply filters
    if search_query:
        query = query.filter(Contact.phone_number.like(f'%{search_query}%'))
    if campaign_filter:
        query = query.filter(Contact.campaign_id == int(campaign_filter))
    if status_filter:
        query = query.filter(Contact.status == status_filter)
        
    # Pagination
    pagination = query.order_by(Contact.id.desc()).paginate(page=page, per_page=50, error_out=False)
    # Note: We pass pagination as 'contacts' because template uses contacts.items
    
    # Get available campaigns for filter dropdown
    if current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin'):
        campaigns = Campaign.query.all()
    else:
        campaigns = Campaign.query.filter_by(user_id=current_user.id).all()
        
    return render_template('contacts.html', 
                           contacts=pagination, 
                           pagination=pagination, 
                           campaigns=campaigns, 
                           search_query=search_query, 
                           selected_campaign_id=int(campaign_filter) if campaign_filter else None, 
                           selected_status=status_filter)

@app.route('/contacts/add', methods=['POST'])
@login_required
@requires_permission('contacts', 'edit')
def add_single_contact():
    phone = request.form.get('phone_number')
    name = request.form.get('name')
    campaign_id = request.form.get('campaign_id')
    
    if not phone or not campaign_id:
        flash('رقم الهاتف والحملة مطلوبان', 'danger')
        return redirect(url_for('contacts_page'))
        
    # Verify campaign ownership
    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        flash('الحملة غير موجودة', 'danger')
        return redirect(url_for('contacts_page'))
        
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية الإضافة لهذه الحملة', 'danger')
        return redirect(url_for('contacts_page'))
        
    # Check duplicate
    if Contact.query.filter_by(campaign_id=campaign_id, phone_number=phone).first():
        flash('هذا الرقم موجود بالفعل في هذه الحملة', 'warning')
        return redirect(url_for('contacts_page'))
        
    new_contact = Contact(phone_number=phone, name=name, campaign_id=campaign_id)
    db.session.add(new_contact)
    db.session.commit()
    
    flash('تم إضافة جهة الاتصال بنجاح', 'success')
    return redirect(url_for('contacts_page'))

@app.route('/contacts/update', methods=['POST'])
@login_required
@requires_permission('contacts', 'edit')
def update_contact():
    contact_id = request.form.get('contact_id')
    phone = request.form.get('phone_number')
    name = request.form.get('name')
    campaign_id = request.form.get('campaign_id')
    status = request.form.get('status')
    return_url = request.form.get('return_url')
    
    contact = Contact.query.get_or_404(contact_id)
    
    # Check ownership (of old campaign)
    old_campaign = Campaign.query.get(contact.campaign_id)
    if old_campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
         flash('لا تملك صلاحية تعديل هذا الرقم', 'danger')
         return redirect(return_url or url_for('contacts_page'))
         
    # Check ownership (of new campaign if changed)
    if int(campaign_id) != contact.campaign_id:
        new_campaign = Campaign.query.get(campaign_id)
        if new_campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
             flash('لا تملك صلاحية النقل لهذه الحملة', 'danger')
             return redirect(return_url or url_for('contacts_page'))
    
    contact.phone_number = phone
    contact.name = name
    contact.campaign_id = campaign_id
    if status:
        contact.status = status
        # If status is changed to pending or retry, we might want to reset retries?
        # For now, just set status.
    
    db.session.commit()
    flash('تم تحديث جهة الاتصال بنجاح', 'success')
    return redirect(return_url or url_for('contacts_page'))

@app.route('/contacts/delete/<int:contact_id>')
@login_required
@requires_permission('contacts', 'edit')
def delete_contact_route(contact_id):
    return delete_contact(contact_id)

@app.route('/contacts/bulk_delete', methods=['POST'])
@login_required
@requires_permission('contacts', 'edit')
def bulk_delete_contacts():
    contact_ids_str = request.form.get('contact_ids')
    if not contact_ids_str:
        flash('لم يتم تحديد أي جهات اتصال', 'warning')
        return redirect(url_for('contacts_page'))
        
    try:
        contact_ids = json.loads(contact_ids_str)
        if not contact_ids:
            flash('لم يتم تحديد أي جهات اتصال', 'warning')
            return redirect(url_for('contacts_page'))
            
        # Verify ownership for all contacts before deleting
        # Efficient way: query all contacts and check ownership
        contacts = Contact.query.filter(Contact.id.in_(contact_ids)).all()
        deleted_count = 0
        
        for contact in contacts:
            # Check permission via campaign ownership
            campaign = Campaign.query.get(contact.campaign_id)
            if campaign and (campaign.user_id == current_user.id or current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')):
                db.session.delete(contact)
                deleted_count += 1
                
        db.session.commit()
        flash(f'تم حذف {deleted_count} جهة اتصال بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ أثناء الحذف: {str(e)}', 'danger')
        
    return redirect(url_for('contacts_page'))

@app.route('/contacts/assign', methods=['POST'])
@login_required
@requires_permission('contacts', 'edit')
def assign_contacts():
    contact_ids_str = request.form.get('contact_ids')
    target_campaign_id = request.form.get('target_campaign_id')
    
    if not contact_ids_str or not target_campaign_id:
        flash('بيانات غير مكتملة', 'warning')
        return redirect(url_for('contacts_page'))
        
    # Verify target campaign ownership
    target_campaign = Campaign.query.get(target_campaign_id)
    if not target_campaign:
        flash('الحملة المستهدفة غير موجودة', 'danger')
        return redirect(url_for('contacts_page'))
        
    if target_campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية النقل لهذه الحملة', 'danger')
        return redirect(url_for('contacts_page'))
        
    try:
        contact_ids = json.loads(contact_ids_str)
        contacts = Contact.query.filter(Contact.id.in_(contact_ids)).all()
        updated_count = 0
        
        for contact in contacts:
             # Check source permission
            source_campaign = Campaign.query.get(contact.campaign_id)
            if source_campaign and (source_campaign.user_id == current_user.id or current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')):
                # Check for duplicate in target
                if not Contact.query.filter_by(campaign_id=target_campaign_id, phone_number=contact.phone_number).first():
                    contact.campaign_id = target_campaign_id
                    updated_count += 1
                
        db.session.commit()
        flash(f'تم نقل {updated_count} جهة اتصال بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ أثناء النقل: {str(e)}', 'danger')
        
    return redirect(url_for('contacts_page'))

# --- إدارة جهات الاتصال (Old Routes) ---
@app.route('/campaign/<int:campaign_id>/view')
@login_required
@requires_permission('contacts', 'view')
def view_campaign(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Check ownership or admin
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية عرض جهات الاتصال لهذه الحملة', 'danger')
        return redirect(url_for('campaigns'))
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    
    # Build query
    query = Contact.query.filter_by(campaign_id=campaign_id)
    
    if search_query:
        query = query.filter(Contact.phone_number.like(f'%{search_query}%'))
    if status_filter:
        query = query.filter(Contact.status == status_filter)
        
    # Paginate
    pagination = query.order_by(Contact.id.desc()).paginate(page=page, per_page=50, error_out=False)
    
    # Get available campaigns for filter dropdown (required by contacts.html)
    if current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin'):
        campaigns = Campaign.query.all()
    else:
        campaigns = Campaign.query.filter_by(user_id=current_user.id).all()

    # Pass pagination as 'contacts' because template iterates over contacts.items
    return render_template('contacts.html', 
                           campaign=campaign, 
                           contacts=pagination,
                           pagination=pagination,
                           campaigns=campaigns,
                           search_query=search_query,
                           selected_campaign_id=campaign_id,
                           selected_status=status_filter)

@app.route('/campaign/<int:campaign_id>/add_contact', methods=['POST'])
@login_required
@requires_permission('contacts', 'edit')
def add_contact(campaign_id):
    # Check ownership first
    campaign = Campaign.query.get_or_404(campaign_id)
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية إضافة جهات اتصال لهذه الحملة', 'danger')
        return redirect(url_for('campaigns'))
        
    phones_str = request.form.get('phone_numbers')
    if phones_str:
        # تقسيم النص إلى أسطر
        lines = phones_str.splitlines()
        added_count = 0
        for line in lines:
            phone = line.strip()
            if phone:
                # التحقق من عدم التكرار داخل الحملة
                exists = Contact.query.filter_by(campaign_id=campaign_id, phone_number=phone).first()
                if not exists:
                    new_contact = Contact(phone_number=phone, campaign_id=campaign_id)
                    db.session.add(new_contact)
                    added_count += 1
        
        db.session.commit()
        if added_count > 0:
            flash(f'تم إضافة {added_count} رقم بنجاح', 'success')
        else:
            flash('لم يتم إضافة أي أرقام (قد تكون مكررة أو فارغة)', 'warning')
            
    return redirect(url_for('view_campaign', campaign_id=campaign_id))

@app.route('/campaign/<int:campaign_id>/upload', methods=['POST'])
@login_required
@requires_permission('contacts', 'edit')
def upload_contacts(campaign_id):
    # Check ownership first
    campaign = Campaign.query.get_or_404(campaign_id)
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية استيراد جهات اتصال لهذه الحملة', 'danger')
        return redirect(url_for('campaigns'))
        
    file = request.files.get('file')
    if file:
        try:
            stream = file.stream.read().decode("utf-8").splitlines()
            count = 0
            for line in stream:
                parts = line.split(',')
                phone_num = parts[0].strip()
                contact_name = parts[1].strip() if len(parts) > 1 else ""
                if phone_num:
                    # تحقق من عدم التكرار داخل الحملة
                    exists = Contact.query.filter_by(campaign_id=campaign_id, phone_number=phone_num).first()
                    if not exists:
                        contact = Contact(phone_number=phone_num, name=contact_name, campaign_id=campaign_id)
                        db.session.add(contact)
                        count += 1
            db.session.commit()
            flash(f'تم استيراد {count} جهة اتصال بنجاح', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء رفع الملف: {str(e)}', 'danger')
            
    return redirect(url_for('view_campaign', campaign_id=campaign_id))

@app.route('/contact/<int:contact_id>/edit', methods=['POST'])
@login_required
@requires_permission('contacts', 'edit')
def edit_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    contact.phone_number = request.form.get('phone_number')
    contact.status = request.form.get('status')
    try:
        contact.retries = int(request.form.get('retries', 0))
    except:
        pass
        
    db.session.commit()
    flash('تم تحديث بيانات الرقم بنجاح', 'success')
    return redirect(url_for('view_campaign', campaign_id=contact.campaign_id))

@app.route('/contact/<int:contact_id>/delete')
@login_required
@requires_permission('contacts', 'edit')
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    campaign_id = contact.campaign_id
    
    # Check ownership
    campaign = Campaign.query.get(campaign_id)
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('لا تملك صلاحية حذف هذا الرقم', 'danger')
        # Redirect based on referrer
        if 'contacts' in request.referrer:
            return redirect(url_for('contacts_page'))
        return redirect(url_for('view_campaign', campaign_id=campaign_id))

    db.session.delete(contact)
    db.session.commit()
    flash('تم حذف الرقم بنجاح', 'info')
    
    # Smart redirect
    if request.referrer and 'contacts' in request.referrer and 'view' not in request.referrer:
         return redirect(url_for('contacts_page'))
    return redirect(url_for('view_campaign', campaign_id=campaign_id))

@app.route('/contact/<int:contact_id>/block')
@login_required
@requires_permission('contacts', 'edit')
def block_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)

    campaign_id = contact.campaign_id
    
    # Check if already blacklisted
    if Blacklist.query.filter_by(phone_number=contact.phone_number).first():
        flash('الرقم موجود بالفعل في القائمة السوداء', 'warning')
    else:
        # Add to Blacklist
        blacklist_item = Blacklist(
            phone_number=contact.phone_number,
            reason=f"تم الحظر من صفحة الحملة (ID: {campaign_id})"
        )
        db.session.add(blacklist_item)
        
        # Update contact status or delete it?
        # Let's just update status to 'failed' or similar, or delete it from active list?
        # User asked to block, implying adding to blacklist. 
        # Usually blocked numbers shouldn't be in the campaign list to be dialed.
        # We can set status to 'failed' or 'blocked' (if we add that status enum).
        # For now, let's keep it in the list but marked as failed/blocked contextually,
        # or just rely on the blacklist check in the dialer.
        
        # But to be clean, let's also remove it from the current campaign list 
        # OR set its status to something that won't be picked up.
        contact.status = 'failed' # Marking as failed prevents immediate redial
        
        db.session.commit()
        flash(f'تم حظر الرقم {contact.phone_number} وإضافته للقائمة السوداء', 'success')
        
    return redirect(url_for('view_campaign', campaign_id=campaign_id))

@app.route('/campaign/<int:campaign_id>/action/<action_type>')
@login_required
@requires_permission('campaigns', 'edit')
def campaign_action(campaign_id, action_type):
    campaign = Campaign.query.get_or_404(campaign_id)
    # Check ownership/permissions
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
         flash('لا تملك صلاحية لهذه الحملة', 'danger')
         return redirect(url_for('campaigns'))
         
    if action_type == 'retry_failed':
        # Retry Failed (including lower and upper case)
        count = Contact.query.filter_by(campaign_id=campaign_id).filter(func.lower(Contact.status) == 'failed').update({'status': 'pending', 'retries': 0}, synchronize_session=False)
        flash(f'تم إعادة تعيين {count} جهة اتصال (فشل) للمحاولة مرة أخرى', 'success')
    elif action_type == 'retry_congestion':
        # Congestion, Busy, No Answer
        count = Contact.query.filter_by(campaign_id=campaign_id).filter(func.lower(Contact.status).in_(['congestion', 'busy', 'no answer'])).update({'status': 'pending', 'retries': 0}, synchronize_session=False)
        flash(f'تم إعادة تعيين {count} جهة اتصال (مشغول/خارج التغطية) للمحاولة مرة أخرى', 'success')
    elif action_type == 'restart':
        count = Contact.query.filter_by(campaign_id=campaign_id).update({'status': 'pending', 'retries': 0}, synchronize_session=False)
        flash(f'تم إعادة تشغيل الحملة بالكامل ({count} رقم)', 'success')
    
    db.session.commit()
    return redirect(url_for('campaigns'))

# --- الإعدادات ---
@app.route('/settings', methods=['GET', 'POST'])
@login_required
@requires_permission('settings', 'view')
def settings():
    config = Settings.query.first()
    if request.method == 'POST':
        if not current_user.can('settings', 'edit'):
            flash('ليس لديك صلاحية لتعديل الإعدادات', 'danger')
            return redirect(url_for('settings'))
            
        config.ami_host = request.form.get('ami_host')
        config.ami_port = int(request.form.get('ami_port'))
        config.ami_user = request.form.get('ami_user')
        config.ami_secret = request.form.get('ami_secret')
        # config.target_queue = request.form.get('target_queue') # Moved to Campaign
        config.dial_delay = int(request.form.get('dial_delay'))
        try:
            config.concurrent_channels = int(request.form.get('concurrent_channels', 1))
        except:
            config.concurrent_channels = 1
        config.max_retries = int(request.form.get('max_retries', 3))
        config.retry_interval = int(request.form.get('retry_interval', 60))
        config.monitor_extension = request.form.get('monitor_extension', '100')
        
        try:
            config.test_call_limit = int(request.form.get('test_call_limit', 3))
        except:
            config.test_call_limit = 3

        # إعدادات CDR
        config.cdr_db_host = request.form.get('cdr_db_host')
        config.cdr_db_port = int(request.form.get('cdr_db_port'))
        config.cdr_db_user = request.form.get('cdr_db_user')
        config.cdr_db_pass = request.form.get('cdr_db_pass')
        config.cdr_db_name = request.form.get('cdr_db_name')
        config.cdr_table_name = request.form.get('cdr_table_name')
        
        # إعدادات تليجرام (Moved to separate route, but kept here for backward compatibility or if form still sends them)
        # We should probably remove them from here if they are not in the form anymore to avoid overwriting with None
        if request.form.get('telegram_bot_token') is not None:
             config.telegram_bot_token = request.form.get('telegram_bot_token')
             config.telegram_chat_id = request.form.get('telegram_chat_id')
             config.telegram_notify_start_stop = 'telegram_notify_start_stop' in request.form
             config.telegram_notify_progress = 'telegram_notify_progress' in request.form
             config.telegram_notify_each_call = 'telegram_notify_each_call' in request.form
             try:
                 config.telegram_notify_interval = int(request.form.get('telegram_notify_interval', 30))
             except:
                 config.telegram_notify_interval = 30

        db.session.commit()
        flash('تم حفظ الإعدادات بنجاح', 'success')
    return render_template('settings.html', settings=config)

@app.route('/settings/telegram', methods=['GET', 'POST'])
@login_required
@requires_permission('settings', 'view')
def telegram_settings():
    config = Settings.query.first()
    if request.method == 'POST':
        if not current_user.can('settings', 'edit'):
            flash('ليس لديك صلاحية لتعديل الإعدادات', 'danger')
            return redirect(url_for('telegram_settings'))
            
        config.telegram_bot_token = request.form.get('telegram_bot_token')
        config.telegram_chat_id = request.form.get('telegram_chat_id')
        config.telegram_notify_start_stop = 'telegram_notify_start_stop' in request.form
        config.telegram_notify_progress = 'telegram_notify_progress' in request.form
        config.telegram_notify_each_call = 'telegram_notify_each_call' in request.form
        try:
            config.telegram_notify_interval = int(request.form.get('telegram_notify_interval', 30))
        except:
            config.telegram_notify_interval = 30
            
        # Templates
        config.telegram_template_start = request.form.get('telegram_template_start')
        config.telegram_template_finish = request.form.get('telegram_template_finish')
        config.telegram_template_progress = request.form.get('telegram_template_progress')

        db.session.commit()
        flash('تم حفظ إعدادات تليجرام بنجاح', 'success')
        
    return render_template('telegram_settings.html', settings=config)

@app.route('/test_telegram')
@login_required
@requires_permission('settings', 'edit')
def test_telegram():
    config = Settings.query.first()
    if not config or not config.telegram_bot_token or not config.telegram_chat_id:
        flash('يرجى حفظ إعدادات تليجرام أولاً', 'warning')
        return redirect(url_for('settings'))
    
    msg = "🔔 *TEST ALERT!* 🚀\n\nThis is a test notification from **Wasel Auto Dialer**. \n\n✅ *Connection Successful!* \nYour Telegram integration is working perfectly. Get ready for real-time updates! 🔥"
    if notifications.send_telegram_message(config.telegram_bot_token, config.telegram_chat_id, msg):
        flash('تم إرسال رسالة الاختبار بنجاح، يرجى التحقق من تليجرام', 'success')
    else:
        flash('فشل إرسال الرسالة، يرجى التحقق من التوكن والـ ID', 'danger')
        
    return redirect(url_for('settings'))

# --- المراقبة الحية ---
@app.route('/monitor')
@login_required
@requires_permission('monitor', 'view')
def monitor():
    return render_template('monitor.html')

@app.route('/api/dongles')
@login_required
@requires_permission('monitor', 'view')
def api_dongles():
    """
    نقطة نهاية API لجلب حالة الدونجلات
    """
    # Check granular permission
    if not current_user.can('monitor_dongles', 'view'):
        return jsonify([])

    settings = Settings.query.first()
    if not settings:
        return jsonify([])
    
    ami = SimpleAMI(settings.ami_host, settings.ami_port, settings.ami_user, settings.ami_secret)
    statuses = ami.get_dongle_statuses()
    return jsonify(statuses)

@app.route('/api/monitor_advanced')
@login_required
@requires_permission('monitor', 'view')
def api_monitor_advanced():
    """
    API endpoint to fetch advanced monitor stats (Queues, Trunks)
    """
    settings = Settings.query.first()
    if not settings:
        return jsonify({'queues': [], 'trunks': []})
    
    ami = SimpleAMI(settings.ami_host, settings.ami_port, settings.ami_user, settings.ami_secret)
    
    queues = []
    if current_user.can('monitor_queues', 'view'):
        queues = ami.get_queue_status()
        
    trunks = []
    if current_user.can('monitor_trunks', 'view'):
        trunks = ami.get_trunk_status()
    
    return jsonify({'queues': queues, 'trunks': trunks})

@app.route('/api/monitor_spy', methods=['POST'])
@login_required
@requires_permission('monitor', 'view')
def api_monitor_spy():
    """
    API endpoint to initiate a spy call
    """
    target_channel = request.form.get('channel')
    option = request.form.get('option', 'q') # q=quiet (listen only), w=whisper, B=barge
    
    if not target_channel:
        return jsonify({'success': False, 'message': 'Target channel is required'})

    settings = Settings.query.first()
    if not settings:
        return jsonify({'success': False, 'message': 'Settings not found'})

    ami = SimpleAMI(settings.ami_host, settings.ami_port, settings.ami_user, settings.ami_secret)
    
    # Use monitor_extension from settings
    spy_ext = settings.monitor_extension or '100'
    
    success = ami.spy_channel(spy_ext, target_channel, option)
    
    if success:
         return jsonify({'success': True, 'message': f'Spying on {target_channel} via {spy_ext}'})
    else:
         return jsonify({'success': False, 'message': 'Failed to initiate spy call'})

@app.route('/api/recent_activity')
@login_required
@requires_permission('monitor', 'view')
def api_recent_activity():
    """
    جلب آخر النشاطات (آخر أرقام تم الاتصال بها)
    """
    # التحقق من صلاحية الأدمن
    is_admin = current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')

    # البحث عن آخر 10 أرقام تم تحديثها (ليست pending)
    if is_admin:
        contacts = Contact.query.filter(Contact.status != 'pending').order_by(Contact.last_dialed.desc()).limit(10).all()
    else:
        contacts = Contact.query.join(Campaign).filter(
            Campaign.user_id == current_user.id,
            Contact.status != 'pending'
        ).order_by(Contact.last_dialed.desc()).limit(10).all()
    
    activities = []
    for contact in contacts:
        if contact.last_dialed:
            time_diff = datetime.now() - contact.last_dialed
            if time_diff.total_seconds() < 60:
                time_str = "منذ لحظات"
            elif time_diff.total_seconds() < 3600:
                time_str = f"منذ {int(time_diff.total_seconds() / 60)} دقيقة"
            else:
                time_str = contact.last_dialed.strftime('%H:%M:%S')
                
            status_text = "غير معروف"
            status_class = "secondary"
            icon = "question"
            
            if contact.status == 'dialed':
                status_text = "جاري الاتصال..."
                status_class = "info"
                icon = "phone"
            elif contact.status == 'answered':
                status_text = f"تم الرد ({contact.duration}s)"
                status_class = "success"
                icon = "check"
            elif contact.status == 'failed':
                status_text = "فشل / لم يتم الرد"
                status_class = "danger"
                icon = "times"
            elif contact.status == 'retry':
                status_text = f"إعادة محاولة ({contact.retries})"
                status_class = "warning"
                icon = "redo"
                
            activities.append({
                'phone': contact.phone_number,
                'status_text': status_text,
                'status_class': status_class,
                'time': time_str,
                'icon': icon
            })
            
    return jsonify(activities)

@app.route('/api/stats')
@login_required
@requires_permission('monitor', 'view')
def api_stats():
    """
    نقطة نهاية API لإرجاع إحصائيات حية بتنسيق JSON
    """
    # التحقق من صلاحية الأدمن
    is_admin = current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')

    # البحث عن الحملة النشطة حالياً
    query = Campaign.query.filter_by(status='active')
    if not is_admin:
        query = query.filter_by(user_id=current_user.id)
        
    active_campaign = query.first()
    
    if active_campaign:
        total = Contact.query.filter_by(campaign_id=active_campaign.id).count()
        pending = Contact.query.filter_by(campaign_id=active_campaign.id, status='pending').count()
        dialed = Contact.query.filter_by(campaign_id=active_campaign.id, status='dialed').count()
        answered = Contact.query.filter_by(campaign_id=active_campaign.id, status='answered').count()
        failed = Contact.query.filter_by(campaign_id=active_campaign.id, status='failed').count()
        
        return jsonify({
            'status': 'active',
            'campaign_id': active_campaign.id,
            'campaign_name': active_campaign.name,
            'total': total,
            'pending': pending,
            'dialed': dialed,
            'answered': answered,
            'failed': failed
        })
    else:
        # Check for paused campaign
        paused_campaign = Campaign.query.filter_by(status='paused', user_id=current_user.id if not is_admin else Campaign.user_id).order_by(Campaign.id.desc()).first()
        if paused_campaign:
             total = Contact.query.filter_by(campaign_id=paused_campaign.id).count()
             pending = Contact.query.filter_by(campaign_id=paused_campaign.id, status='pending').count()
             dialed = Contact.query.filter_by(campaign_id=paused_campaign.id, status='dialed').count()
             answered = Contact.query.filter_by(campaign_id=paused_campaign.id, status='answered').count()
             failed = Contact.query.filter_by(campaign_id=paused_campaign.id, status='failed').count()
             return jsonify({
                'status': 'paused',
                'campaign_id': paused_campaign.id,
                'campaign_name': paused_campaign.name,
                'total': total,
                'pending': pending,
                'dialed': dialed,
                'answered': answered,
                'failed': failed
            })
            
        # إذا لم تكن هناك حملة نشطة، نرجع إجماليات عامة أو حالة خاملة
        return jsonify({
            'status': 'idle',
            'campaign_id': None,
            'campaign_name': 'لا توجد حملة نشطة',
            'total': 0,
            'pending': 0,
            'dialed': 0,
            'answered': 0,
            'failed': 0
        })

@app.route('/api/campaign/<int:campaign_id>/status', methods=['POST'])
@login_required
@requires_permission('campaigns', 'edit')
def api_campaign_status(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Check ownership or admin
    if campaign.user_id != current_user.id and current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        return jsonify({'success': False, 'message': 'Permission denied'})

    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['active', 'paused']:
        return jsonify({'success': False, 'message': 'Invalid status'})
        
    # Check if locked
    if campaign.is_locked:
         is_admin = current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')
         if not is_admin:
             return jsonify({'success': False, 'message': 'Campaign is locked by admin'})

    campaign.status = new_status
    db.session.commit()
    
    # Send notification if needed (reusing logic)
    config = Settings.query.first()
    if config and config.telegram_bot_token and config.telegram_chat_id and config.telegram_notify_start_stop:
        msg = notifications.format_campaign_status_message(campaign.name, campaign.status)
        notifications.send_telegram_message(config.telegram_bot_token, config.telegram_chat_id, msg)

    return jsonify({'success': True, 'message': f'Campaign status updated to {new_status}'})


@app.route('/logs')
@login_required
@requires_permission('system_logs', 'view')
def view_logs():
    return render_template('logs.html')

@app.route('/api/logs')
@login_required
@requires_permission('system_logs', 'view')
def get_logs():
    try:
        log_file_path = os.path.join(os.getcwd(), 'dialer.log')
        if not os.path.exists(log_file_path):
            return jsonify({'logs': ['Log file not found.']})
        
        # قراءة آخر 100 سطر
        with open(log_file_path, 'r', encoding='utf-8') as f:
            # طريقة فعالة لقراءة آخر الأسطر للملفات الكبيرة
            lines = f.readlines()
            last_lines = lines[-100:]
            
            # تلوين السطور (اختياري لتحسين العرض)
            formatted_lines = []
            for line in last_lines:
                line = line.strip()
                if 'ERROR' in line:
                    formatted_lines.append(f'<span class="text-danger">{line}</span>')
                elif 'WARNING' in line:
                    formatted_lines.append(f'<span class="text-warning">{line}</span>')
                elif 'INFO' in line:
                    formatted_lines.append(f'<span class="text-success">{line}</span>')
                else:
                    formatted_lines.append(f'<span class="text-white">{line}</span>')
            
            return jsonify({'logs': formatted_lines})
    except Exception as e:
        return jsonify({'logs': [f'Error reading logs: {str(e)}']})

# --- إدارة المستخدمين ---
@app.route('/users')
@login_required
@requires_permission('users', 'view')
def users():
    users = User.query.all()
    roles = Role.query.all()
    return render_template('users.html', users=users, roles=roles)

@app.route('/users/add', methods=['POST'])
@login_required
@requires_permission('users', 'edit')
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role_id = request.form.get('role_id')
    
    if User.query.filter_by(username=username).first():
        flash('اسم المستخدم مسجل بالفعل', 'danger')
        return redirect(url_for('users'))
    
    # تحديد الدور القديم (legacy role) بناءً على الدور المختار
    # إذا كان الدور المختار هو Admin (بالاسم)، نجعله admin في العمود القديم أيضاً
    legacy_role = 'user'
    selected_role = Role.query.get(role_id)
    if selected_role and selected_role.name == 'Admin':
        legacy_role = 'admin'

    # إنشاء العميل أولاً (إذا تم إدخال بياناته)
    client_name = request.form.get('client_name')
    company_name = request.form.get('company_name')
    phone = request.form.get('phone')
    communication_method = request.form.get('communication_method')
    notes = request.form.get('notes')
    
    new_client = None
    if client_name and phone:
        new_client = Client(
            name=client_name,
            company_name=company_name,
            phone=phone,
            communication_method=communication_method,
            notes=notes
        )
        db.session.add(new_client)
        db.session.flush() # للحصول على الـ ID

    new_user = User(username=username, role_id=role_id, role=legacy_role)
    if new_client:
        new_user.client_id = new_client.id
        
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    flash('تم إضافة المستخدم بنجاح', 'success')
    return redirect(url_for('users'))

@app.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@requires_permission('users', 'edit')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    user.username = request.form.get('username')
    user.role_id = request.form.get('role_id')
    
    role_obj = Role.query.get(user.role_id)
    if role_obj and role_obj.name == 'Admin':
        user.role = 'admin'
    else:
        user.role = 'user'
    
    password = request.form.get('password')
    if password:
        user.set_password(password)
        
    # تحديث أو إنشاء بيانات العميل
    client_name = request.form.get('client_name')
    company_name = request.form.get('company_name')
    phone = request.form.get('phone')
    communication_method = request.form.get('communication_method')
    notes = request.form.get('notes')
    
    if client_name and phone:
        if user.client:
            user.client.name = client_name
            user.client.company_name = company_name
            user.client.phone = phone
            user.client.communication_method = communication_method
            user.client.notes = notes
        else:
            new_client = Client(
                name=client_name,
                company_name=company_name,
                phone=phone,
                communication_method=communication_method,
                notes=notes
            )
            db.session.add(new_client)
            db.session.flush()
            user.client_id = new_client.id
            
    db.session.commit()
    flash('تم تحديث بيانات المستخدم بنجاح', 'success')
    return redirect(url_for('users'))

@app.route('/users/<int:user_id>/delete')
@login_required
@requires_permission('users', 'edit')
def delete_user(user_id):
    if user_id == current_user.id:
        flash('لا يمكنك حذف نفسك!', 'warning')
        return redirect(url_for('users'))
        
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('تم حذف المستخدم بنجاح', 'info')
    return redirect(url_for('users'))

# --- Roles Management Routes ---
@app.route('/roles')
@login_required
@requires_permission('roles', 'view')
def roles():
    roles = Role.query.all()
    return render_template('roles.html', roles=roles)

@app.route('/roles/add', methods=['POST'])
@login_required
@requires_permission('roles', 'edit')
def add_role():
    name = request.form.get('name')
    if Role.query.filter_by(name=name).first():
        flash('اسم الدور موجود بالفعل', 'danger')
        return redirect(url_for('roles'))
    
    perms = {}
    resources = ['campaigns', 'contacts', 'monitor', 'settings', 'users', 'roles', 'monitor_queues', 'monitor_trunks', 'monitor_dongles', 'database', 'packages', 'command_screen', 'test_call', 'system_logs', 'cdr_import', 'reports']
    for res in resources:
        perms[res] = request.form.get(f'perm_{res}', 'none')
        
    new_role = Role(name=name)
    new_role.set_permissions(perms)
    db.session.add(new_role)
    db.session.commit()
    flash('تم إضافة الدور بنجاح', 'success')
    return redirect(url_for('roles'))

@app.route('/roles/<int:role_id>/edit', methods=['POST'])
@login_required
@requires_permission('roles', 'edit')
def edit_role(role_id):
    role = Role.query.get_or_404(role_id)
    role.name = request.form.get('name')
    
    perms = {}
    resources = ['campaigns', 'contacts', 'monitor', 'settings', 'users', 'roles', 'monitor_queues', 'monitor_trunks', 'monitor_dongles', 'database', 'packages', 'command_screen', 'test_call', 'system_logs', 'cdr_import', 'reports']
    for res in resources:
        perms[res] = request.form.get(f'perm_{res}', 'none')
        
    role.set_permissions(perms)
    db.session.commit()
    flash('تم تحديث الدور بنجاح', 'success')
    return redirect(url_for('roles'))

@app.route('/roles/<int:role_id>/delete')
@login_required
@requires_permission('roles', 'edit')
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    if role.name == 'Admin':
        flash('لا يمكن حذف دور المسؤول', 'danger')
        return redirect(url_for('roles'))
    
    if role.users:
        flash('لا يمكن حذف هذا الدور لأنه مستخدم من قبل بعض المستخدمين', 'warning')
        return redirect(url_for('roles'))
        
    db.session.delete(role)
    db.session.commit()
    flash('تم حذف الدور بنجاح', 'success')
    return redirect(url_for('roles'))

# Client routes removed as per user request to consolidate with User Management

# --- Admin Advanced Features ---
@app.route('/campaign/<int:campaign_id>/toggle_lock')
@login_required
@requires_permission('campaigns', 'edit')
def toggle_campaign_lock(campaign_id):
    # Only Admin can lock/unlock
    if current_user.role != 'admin' and (not current_user.user_role or current_user.user_role.name != 'Admin'):
        flash('هذه الميزة متاحة للمسؤولين فقط', 'danger')
        return redirect(url_for('campaigns'))
        
    campaign = Campaign.query.get_or_404(campaign_id)
    
    if campaign.is_locked:
        campaign.is_locked = False
        flash('تم إلغاء قفل الحملة، يمكن للمستخدم التحكم بها الآن', 'success')
    else:
        campaign.is_locked = True
        if campaign.status == 'active':
            campaign.status = 'paused' # Stop it if it's running
        flash('تم قفل الحملة وإيقافها، لا يمكن للمستخدم تشغيلها حتى يتم إلغاء القفل', 'warning')
        
    db.session.commit()
    return redirect(url_for('campaigns'))

@app.route('/campaigns/import_cdr', methods=['POST'])
@login_required
@requires_permission('cdr_import', 'edit')
def import_cdr_to_campaign_route():
    campaign_name = request.form.get('campaign_name')
    if not campaign_name:
        flash('الرجاء تحديد اسم الحملة', 'danger')
        return redirect(url_for('campaigns'))
        
    # Get or Create Campaign
    campaign = Campaign.query.filter_by(name=campaign_name).first()
    if not campaign:
        campaign = Campaign(
            name=campaign_name,
            status='paused',
            target_queue='501',
            user_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(campaign)
        db.session.commit()
        flash(f'تم إنشاء حملة جديدة باسم {campaign_name}', 'info')
    
    # Import Logic
    settings = Settings.query.first()
    if not settings:
        flash('إعدادات النظام غير متوفرة', 'danger')
        return redirect(url_for('campaigns'))
        
    try:
        cdr_conn = pymysql.connect(
            host=settings.cdr_db_host,
            port=settings.cdr_db_port,
            user=settings.cdr_db_user,
            password=settings.cdr_db_pass,
            database=settings.cdr_db_name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5
        )
    except Exception as e:
        flash(f'فشل الاتصال بقاعدة بيانات Asterisk: {str(e)}', 'danger')
        return redirect(url_for('campaigns'))

    try:
        with cdr_conn.cursor() as cursor:
            table_name = settings.cdr_table_name
            # Query grouped by source (Caller ID) as requested
            # Reverting to standard Asterisk columns (src, disposition, billsec) as 'source' column does not exist
            sql = f"""
                SELECT 
                    src, 
                    COUNT(*) as attempts, 
                    MAX(calldate) as last_attempt, 
                    MAX(billsec) as max_duration,
                    SUM(CASE WHEN disposition = 'ANSWERED' THEN 1 ELSE 0 END) as answered_count
                FROM {table_name}
                WHERE src != '' AND src IS NOT NULL
                GROUP BY src
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            
            existing_phones = {c.phone_number for c in Contact.query.filter_by(campaign_id=campaign.id).all()}
            
            new_contacts = []
            count_added = 0
            
            for row in results:
                # Use 'src' column
                phone = str(row['src']).strip()
                
                # Validation: Skip invalid numbers
                # 1. Check length (must fit in DB column)
                if len(phone) > 20:
                    continue
                # 2. Check for alphabetic characters (excludes things like "CALLERID")
                if any(c.isalpha() for c in phone):
                    continue
                # 3. Basic validity check (must have some digits)
                if not any(c.isdigit() for c in phone):
                    continue
                    
                if phone in existing_phones:
                    continue
                    
                status = 'answered' if row['answered_count'] > 0 else 'failed'
                attempts = row['attempts']
                
                contact = Contact(
                    phone_number=phone,
                    status=status,
                    campaign_id=campaign.id,
                    last_dialed=row['last_attempt'],
                    duration=row['max_duration'],
                    retries=attempts,
                    name=f"CDR Import"
                )
                new_contacts.append(contact)
                count_added += 1
                
                if len(new_contacts) >= 1000:
                    db.session.add_all(new_contacts)
                    db.session.commit()
                    new_contacts = []
            
            if new_contacts:
                db.session.add_all(new_contacts)
                db.session.commit()
                
            flash(f'تم استيراد {count_added} جهة اتصال بنجاح إلى الحملة {campaign_name}', 'success')
            
    except Exception as e:
        flash(f'حدث خطأ أثناء الاستيراد: {str(e)}', 'danger')
    finally:
        cdr_conn.close()
        
    return redirect(url_for('campaigns'))

@app.route('/users/<int:user_id>/toggle_ban')
@login_required
@requires_permission('users', 'edit')
def toggle_user_ban(user_id):
    if user_id == current_user.id:
        flash('لا يمكنك حظر نفسك!', 'warning')
        return redirect(url_for('users'))
        
    user = User.query.get_or_404(user_id)
    
    if user.is_banned:
        user.is_banned = False
        flash(f'تم إلغاء حظر المستخدم {user.username}', 'success')
    else:
        user.is_banned = True
        flash(f'تم حظر المستخدم {user.username}', 'warning')
        
    db.session.commit()
    return redirect(url_for('users'))

# --- Blacklist Management ---
@app.route('/blacklist')
@login_required
@requires_permission('settings', 'view')
def blacklist():
    blacklist_items = Blacklist.query.order_by(Blacklist.added_at.desc()).all()
    return render_template('blacklist.html', blacklist_items=blacklist_items)

@app.route('/blacklist/add', methods=['POST'])
@login_required
@requires_permission('settings', 'edit')
def add_blacklist():
    phone_number = request.form.get('phone_number')
    reason = request.form.get('reason')
    
    if not phone_number:
        flash('رقم الهاتف مطلوب', 'danger')
        return redirect(url_for('blacklist'))
    
    # Check if exists
    if Blacklist.query.filter_by(phone_number=phone_number).first():
        flash('هذا الرقم موجود بالفعل في القائمة السوداء', 'warning')
        return redirect(url_for('blacklist'))
        
    new_item = Blacklist(phone_number=phone_number, reason=reason)
    db.session.add(new_item)
    db.session.commit()
    
    flash('تم إضافة الرقم للقائمة السوداء بنجاح', 'success')
    return redirect(url_for('blacklist'))

@app.route('/blacklist/<int:item_id>/delete', methods=['POST'])
@login_required
@requires_permission('settings', 'edit')
def delete_blacklist(item_id):
    item = Blacklist.query.get_or_404(item_id)
    
    # Reset Test Call History for this number so it can be tested again
    try:
        TestCallHistory.query.filter_by(phone_number=item.phone_number).delete()
    except Exception as e:
        # Don't fail the whole operation if history deletion fails
        print(f"Error deleting test call history: {e}")
        
    db.session.delete(item)
    db.session.commit()
    flash('تم حذف الرقم من القائمة السوداء وإعادة تعيين عداد المحاولات', 'success')
    return redirect(url_for('blacklist'))

# --- Reporting Routes ---
@app.route('/reports')
@login_required
@requires_permission('campaigns', 'view')
def reports():
    campaign_id = request.args.get('campaign_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    phone = request.args.get('phone')
    status = request.args.get('status')
    min_duration = request.args.get('min_duration')
    max_duration = request.args.get('max_duration')
    
    # Base query
    query = Contact.query.join(Campaign)
    
    # Filter by User Ownership (if not admin)
    if not (current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')):
         query = query.filter(Campaign.user_id == current_user.id)
         
    # Apply Filters
    if campaign_id:
        query = query.filter(Contact.campaign_id == campaign_id)
        
    if phone:
        query = query.filter(Contact.phone_number.like(f"%{phone}%"))
    
    if status:
        query = query.filter(Contact.status == status)
        
    if min_duration:
        try:
            query = query.filter(Contact.duration >= int(min_duration))
        except ValueError:
            pass

    if max_duration:
        try:
            query = query.filter(Contact.duration <= int(max_duration))
        except ValueError:
            pass
        
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(Contact.last_dialed >= start_date)
        
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        # Add 23:59:59 to end date to include the full day
        end_date = end_date.replace(hour=23, minute=59, second=59)
        query = query.filter(Contact.last_dialed <= end_date)
    
    # Get Data
    # Only get contacts that have been dialed (status != pending) for stats
    # Or should we include pending? usually reports are about what happened.
    # Let's show all contacts matching criteria, but stats based on dialed.
    
    contacts = query.order_by(Contact.last_dialed.desc()).limit(500).all() # Limit for display
    
    # Calculate Stats (Aggregate query for better performance on large datasets)
    # Note: We need a separate query for stats without limit
    stats_query = query.with_entities(
        db.func.count(Contact.id).label('total'),
        db.func.sum(db.case((Contact.status == 'answered', 1), else_=0)).label('answered'),
        db.func.sum(Contact.duration).label('total_duration')
    )
    
    stats_result = stats_query.first()
    
    total_dialed = stats_result.total or 0 # Actually this is total contacts matching filter
    # To be precise, ASR is Answered / Dialed Attempts. 
    # Let's count 'dialed' as status != 'pending'
    
    dialed_attempts_count = query.filter(Contact.status != 'pending').count()
    answered_count = stats_result.answered or 0
    total_duration = stats_result.total_duration or 0
    
    asr = 0
    if dialed_attempts_count > 0:
        asr = round((answered_count / dialed_attempts_count) * 100, 2)
        
    acd = 0
    if answered_count > 0:
        acd = round(total_duration / answered_count, 2)
        
    stats = {
        'total_dialed': dialed_attempts_count,
        'answered': int(answered_count),
        'asr': asr,
        'acd': acd
    }
    
    # Campaigns for dropdown
    if current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin'):
        campaigns = Campaign.query.all()
    else:
        campaigns = Campaign.query.filter_by(user_id=current_user.id).all()
        
    return render_template('reports.html', 
                           contacts=contacts, 
                           stats=stats, 
                           campaigns=campaigns,
                           selected_campaign_id=campaign_id,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           phone=phone,
                           status=status,
                           min_duration=min_duration,
                           max_duration=max_duration)

@app.route('/reports/export')
@login_required
@requires_permission('campaigns', 'view')
def export_report():
    campaign_id = request.args.get('campaign_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    phone = request.args.get('phone')
    status = request.args.get('status')
    min_duration = request.args.get('min_duration')
    max_duration = request.args.get('max_duration')
    
    query = Contact.query.join(Campaign).add_columns(
        Campaign.name.label('campaign_name'),
        Contact.phone_number,
        Contact.status,
        Contact.duration,
        Contact.last_dialed,
        Contact.retries,
        Contact.name.label('contact_name')
    )
    
    if not (current_user.role == 'admin' or (current_user.user_role and current_user.user_role.name == 'Admin')):
         query = query.filter(Campaign.user_id == current_user.id)
         
    if campaign_id:
        query = query.filter(Contact.campaign_id == campaign_id)

    if phone:
        query = query.filter(Contact.phone_number.like(f"%{phone}%"))
    
    if status:
        query = query.filter(Contact.status == status)
        
    if min_duration:
        try:
            query = query.filter(Contact.duration >= int(min_duration))
        except ValueError:
            pass

    if max_duration:
        try:
            query = query.filter(Contact.duration <= int(max_duration))
        except ValueError:
            pass
        
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(Contact.last_dialed >= start_date)
        
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        end_date = end_date.replace(hour=23, minute=59, second=59)
        query = query.filter(Contact.last_dialed <= end_date)
        
    results = query.all()
    
    # Convert to list of dicts
    data = []
    for row in results:
        # row is a tuple (Contact, campaign_name, ...) because of add_columns?
        # Actually join + add_columns returns a KeyedTuple
        contact = row[0] # The Contact object is the first element if not using add_columns exclusively
        # Wait, with add_columns, it returns (Contact, col1, col2...)
        
        data.append({
            'Campaign': row.campaign_name,
            'Name': row.contact_name,
            'Phone': row.phone_number,
            'Status': row.status,
            'Duration (sec)': row.duration,
            'Last Dialed': row.last_dialed,
            'Retries': row.retries
        })
        
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:  # type: ignore
        df.to_excel(writer, index=False, sheet_name='Report')
        
    output.seek(0)
    
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- Real-Time Updates Endpoint (called by dialer_daemon) ---
@app.route('/api/notify/update', methods=['POST'])
def notify_update():
    # Basic security check (localhost only or shared secret)
    # For now, we assume internal call
    data = request.json
    event_type = data.get('type')
    payload = data.get('payload')
    
    if event_type:
        socketio.emit(event_type, payload)
        
    return jsonify({'status': 'ok'})

# --- Database Management ---
@app.route('/database')
@login_required
@requires_permission('database', 'view')
def database_page():
    # Calculate DB size
    db_path = os.path.join(app.instance_path, 'autodialer.db')
    size_str = "0 KB"
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        if size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.2f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
            
    # Statistics
    stats = {
        'campaigns': Campaign.query.count(),
        'contacts': Contact.query.count(),
        'users': User.query.count(),
        'blacklist': Blacklist.query.count(),
        'roles': Role.query.count()
    }
            
    return render_template('database.html', db_size=size_str, stats=stats)

@app.route('/database/optimize')
@login_required
@requires_permission('database', 'edit')
def optimize_database():
    try:
        # For SQLite, VACUUM command rebuilds the database file, repacking it into a minimal amount of disk space
        db.session.execute('VACUUM')
        db.session.commit()
        flash('تم تحسين قاعدة البيانات بنجاح (VACUUM)', 'success')
    except Exception as e:
        flash(f'حدث خطأ أثناء التحسين: {str(e)}', 'error')
        
    return redirect(url_for('database_page'))

@app.route('/database/export')
@login_required
@requires_permission('database', 'view') # View permission is enough to export/backup
def export_database():
    db_path = os.path.join(app.instance_path, 'autodialer.db')
    if not os.path.exists(db_path):
        flash('ملف قاعدة البيانات غير موجود', 'error')
        return redirect(url_for('database_page'))
        
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"backup_autodialer_{timestamp}.db"
    
    return send_file(
        db_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/x-sqlite3'
    )

@app.route('/database/import', methods=['POST'])
@login_required
@requires_permission('database', 'edit')
def import_database():
    if 'db_file' not in request.files:
        flash('لم يتم اختيار ملف', 'error')
        return redirect(url_for('database_page'))
        
    file = request.files['db_file']
    if file.filename == '':
        flash('لم يتم اختيار ملف', 'error')
        return redirect(url_for('database_page'))
        
    if file and file.filename.endswith('.db'):
        # Create a backup of the current DB first
        db_path = os.path.join(app.instance_path, 'autodialer.db')
        backup_path = os.path.join(app.instance_path, f'autodialer_pre_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
        
        try:
            if os.path.exists(db_path):
                shutil.copy2(db_path, backup_path)
                
            # Save the new file
            file.save(db_path)
            flash('تم استعادة قاعدة البيانات بنجاح', 'success')
            
            # Restart mechanism might be needed here if the app caches DB connections
            # But for SQLite with Flask-SQLAlchemy, it usually handles new connections per request
            
        except Exception as e:
            flash(f'حدث خطأ أثناء الاستعادة: {str(e)}', 'error')
            # Try to restore from backup if things went wrong
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, db_path)
    else:
        flash('نوع الملف غير مدعوم. يرجى رفع ملف .db', 'error')
        
    return redirect(url_for('database_page'))

@app.route('/database/import_local', methods=['POST'])
@login_required
@requires_permission('database', 'edit')
def import_database_local():
    file_path = request.form.get('file_path')
    if not file_path:
        flash('يرجى تحديد مسار الملف', 'error')
        return redirect(url_for('database_page'))
        
    if not os.path.exists(file_path):
        flash('الملف غير موجود في المسار المحدد', 'error')
        return redirect(url_for('database_page'))
        
    if not file_path.endswith('.db'):
        flash('يجب أن يكون الملف بصيغة .db', 'error')
        return redirect(url_for('database_page'))
        
    # Create a backup of the current DB first
    db_path = os.path.join(app.instance_path, 'autodialer.db')
    backup_path = os.path.join(app.instance_path, f'autodialer_pre_restore_local_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    
    try:
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
            
        # Copy the file from local path
        shutil.copy2(file_path, db_path)
        flash('تم استعادة قاعدة البيانات بنجاح من المسار المحلي', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ أثناء الاستعادة: {str(e)}', 'error')
        # Try to restore from backup if things went wrong
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, db_path)
            
    return redirect(url_for('database_page'))

@app.route('/packages')
@login_required
@requires_permission('packages', 'view')
def packages_page():
    return render_template('packages.html')

# --- Command Screen (SSH Terminal) ---
@app.route('/command_screen')
@login_required
@requires_permission('command_screen', 'view')
def command_screen():
    settings = Settings.query.first()
    return render_template('command_screen.html', settings=settings)

# SocketIO Events for SSH
@socketio.on('connect_ssh')
def handle_connect_ssh(data):
    if not current_user.is_authenticated or not current_user.can('command_screen', 'view'):
        emit('ssh_status', {'status': 'error', 'message': 'Unauthorized'})
        return

    host = data.get('host')
    port = data.get('port', 22)
    username = data.get('username')
    password = data.get('password')
    cols = data.get('cols', 80)
    rows = data.get('rows', 24)

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, port=port, username=username, password=password)
        
        # Invoke shell
        channel = ssh.invoke_shell(term='xterm', width=cols, height=rows)
        
        ssh_sessions[request.sid] = {
            'ssh': ssh,
            'channel': channel,
            'thread': None
        }
        
        def listen_to_ssh(sid):
            while True:
                try:
                    if sid not in ssh_sessions:
                        break
                    channel = ssh_sessions[sid]['channel']
                    if channel.recv_ready():
                        data = channel.recv(1024).decode('utf-8')
                        socketio.emit('ssh_output', {'data': data}, room=sid)
                    elif channel.exit_status_ready():
                        break
                    else:
                        socketio.sleep(0.1)
                except Exception as e:
                    break
            
            # Cleanup on exit
            if sid in ssh_sessions:
                try:
                    ssh_sessions[sid]['ssh'].close()
                except:
                    pass
                del ssh_sessions[sid]
            socketio.emit('ssh_status', {'status': 'disconnected'}, room=sid)

        # Start listener thread
        thread = socketio.start_background_task(listen_to_ssh, request.sid)
        ssh_sessions[request.sid]['thread'] = thread
        
        emit('ssh_status', {'status': 'connected'})
        
    except Exception as e:
        emit('ssh_status', {'status': 'error', 'message': str(e)})

@socketio.on('ssh_input')
def handle_ssh_input(data):
    if request.sid in ssh_sessions:
        try:
            ssh_sessions[request.sid]['channel'].send(data['data'])
        except:
            pass

@socketio.on('resize')
def handle_resize(data):
    if request.sid in ssh_sessions:
        try:
            ssh_sessions[request.sid]['channel'].resize_pty(width=data['cols'], height=data['rows'])
        except:
            pass

@socketio.on('disconnect_ssh')
def handle_disconnect_ssh():
    if request.sid in ssh_sessions:
        try:
            ssh_sessions[request.sid]['ssh'].close()
        except:
            pass
        del ssh_sessions[request.sid]
        emit('ssh_status', {'status': 'disconnected'})

@socketio.on('disconnect')
def handle_disconnect():
    handle_disconnect_ssh()

@app.route('/test_call_501', methods=['GET', 'POST'])
@login_required
@requires_permission('test_call', 'view')
def test_call_501():
    if request.method == 'POST':
        phone = request.form.get('phone')
        if not phone:
            flash('الرجاء إدخال رقم الهاتف', 'danger')
            return redirect(url_for('test_call_501'))
            
        settings = Settings.query.first()
        if not settings:
             flash('خطأ: إعدادات النظام غير متوفرة', 'danger')
             return redirect(url_for('test_call_501'))
             
        ami = SimpleAMI(settings.ami_host, settings.ami_port, settings.ami_user, settings.ami_secret)
        if ami.connect():
            # التحقق من الحد المسموح
            current_count = TestCallHistory.query.filter_by(phone_number=phone).count()
            limit = settings.test_call_limit if settings.test_call_limit else 1
            
            # إذا تجاوز الحد ولم يكن محظوراً (حالة نادرة أو تم تغيير الحد)
            if current_count >= limit:
                existing = Blacklist.query.filter_by(phone_number=phone).first()
                if not existing:
                    new_entry = Blacklist(
                        phone_number=phone,
                        reason='تم تجاوز حد الاتصال التجريبي',
                        blocked_by=current_user.username if hasattr(current_user, 'username') else 'Unknown'
                    )
                    db.session.add(new_entry)
                    db.session.commit()
                    flash(f'تم تجاوز الحد المسموح ({limit}) لهذا الرقم وتم حظره.', 'warning')
                else:
                    flash(f'هذا الرقم محظور بالفعل وتجاوز الحد المسموح ({limit}).', 'warning')
                return redirect(url_for('test_call_501'))

            channel = f"Local/{phone}@from-internal"
            
            success, ami_response = ami.originate_call_with_response(
                channel=channel,
                exten='501',
                context='from-internal',
                priority=1,
                caller_id='TestCall <501>'
            )
            
            if success:
                # تسجيل المحاولة
                hist = TestCallHistory(phone_number=phone, user_id=current_user.id)
                db.session.add(hist)
                
                # التحقق هل وصلنا للحد الأقصى بعد هذه المحاولة
                if current_count + 1 >= limit:
                    existing = Blacklist.query.filter_by(phone_number=phone).first()
                    if not existing:
                        new_entry = Blacklist(
                            phone_number=phone,
                            reason='تم إجراء الإتصال التجريبي (تجاوز الحد)',
                            blocked_by=current_user.username if hasattr(current_user, 'username') else 'Unknown'
                        )
                        db.session.add(new_entry)
                        db.session.commit()
                        flash(f'تم بدء الاتصال بالرقم {phone} (المحاولة {current_count + 1}/{limit}) وإضافته لقائمة الحظر.', 'success')
                    else:
                        db.session.commit() # لحفظ السجل
                        flash(f'تم بدء الاتصال بالرقم {phone}. الرقم موجود بالفعل في قائمة الحظر.', 'warning')
                else:
                    db.session.commit()
                    flash(f'تم بدء الاتصال بالرقم {phone} (المحاولة {current_count + 1}/{limit}).', 'success')
            else:
                # تنظيف الرد لعرضه
                clean_response = ami_response.replace('\r\n', ' ').replace('Response:', '').strip()
                flash(f'فشل إرسال أمر الاتصال. رد Asterisk: {clean_response}', 'danger')
                
        else:
            flash('فشل الاتصال بـ AMI. تأكد من تشغيل Asterisk والإعدادات.', 'danger')
    return render_template('test_call_501.html')

if __name__ == '__main__':
    # لتفعيل الوصول الخارجي، نستخدم host='0.0.0.0'
    # ملاحظة: إذا لم يعمل الدومين، تحقق من إعدادات الجدار الناري (Firewall) على السيرفر
    # الأمر المقترح لفتح المنفذ على CentOS/Issabel:
    # firewall-cmd --zone=public --add-port=5000/tcp --permanent && firewall-cmd --reload
    print("Starting server on 0.0.0.0:5000...")
    # app.run(host='0.0.0.0', port=5000, debug=True)
    try:
        # محاولة التشغيل بالمعاملات الحديثة
        socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
    except TypeError:
        # التراجع للتوافق مع الإصدارات القديمة (Python 3.6 / Flask القديم)
        print("Fallback to legacy socketio.run arguments...")
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
