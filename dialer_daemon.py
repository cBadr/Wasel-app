import time
import socket
import re
import os
import threading
import logging
import sys
import pymysql
import requests
import json
import notifications
from datetime import datetime, timedelta
from sqlalchemy import create_engine, or_, and_
from sqlalchemy.orm import sessionmaker
from concurrent.futures import ThreadPoolExecutor
from models import Settings, Campaign, Contact, Blacklist, db
from ami_client import SimpleAMI

# إعداد نظام التسجيل (Logging)
# يتم التسجيل في ملف dialer.log وأيضاً طباعة المخرجات على الشاشة
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("dialer.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# إعداد الاتصال بقاعدة البيانات
# نستخدم مسار مطلق لملف قاعدة البيانات في مجلد instance
# db_path = f'sqlite:///{os.path.join(os.getcwd(), "instance", "autodialer.db")}'
# engine = create_engine(db_path)
db_uri = 'mysql+pymysql://root:Medoza120a@officex2.ddns.net/wasel'
engine = create_engine(db_uri, pool_recycle=280)
Session = sessionmaker(bind=engine)

def notify_server(event_type, payload):
    """
    إرسال إشعار فوري للسيرفر عبر API لتحديث الواجهة
    """
    try:
        url = "http://127.0.0.1:5000/api/notify/update"
        requests.post(url, json={'type': event_type, 'payload': payload}, timeout=1)
    except Exception:
        pass # تجاهل الأخطاء لعدم تعطيل الدايلر

def sync_cdr_data(session, settings):
    """
    مزامنة سجلات المكالمات من قاعدة بيانات Asterisk CDR
    """
    try:
        # الاتصال بقاعدة بيانات CDR
        conn = pymysql.connect(
            host=settings.cdr_db_host,
            port=settings.cdr_db_port,
            user=settings.cdr_db_user,
            password=settings.cdr_db_pass,
            database=settings.cdr_db_name,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5
        )
        
        with conn.cursor() as cursor:
            # البحث عن جهات الاتصال التي حالتها 'dialed' ولم يتم تحديث مدتها
            # نوسع نافذة البحث لتشمل آخر 3 ساعات لضمان عدم فقدان أي مكالمة
            three_hours_ago = datetime.now() - timedelta(hours=3)
            contacts = session.query(Contact).filter(
                Contact.status == 'dialed',
                Contact.last_dialed >= three_hours_ago
            ).all()
            
            if contacts:
                logger.info(f"جاري مزامنة CDR لعدد {len(contacts)} جهة اتصال معلقة...")
            
            for contact in contacts:
                dial_time = contact.last_dialed
                
                # توسيع نافذة البحث في CDR (قبل وبعد وقت الاتصال)
                # أحياناً يكون وقت السيرفر مختلف قليلاً
                search_start = dial_time - timedelta(minutes=60)
                
                # محاولة 1: البحث برقم الهاتف كما هو (أو كجزء من الرقم)
                # نستخدم % في البداية لأن الرقم في قاعدة البيانات قد يحتوي على بادئة
                search_phone = f"%{contact.phone_number}"
                
                sql = f"""
                    SELECT billsec, disposition, calldate 
                    FROM {settings.cdr_table_name} 
                    WHERE dst LIKE %s 
                    AND calldate >= %s 
                    ORDER BY calldate DESC LIMIT 1
                """
                
                cursor.execute(sql, (search_phone, search_start))
                result = cursor.fetchone()
                
                # محاولة 2: إذا لم نجد، نحاول بآخر 9 أرقام (لتجاوز مشاكل البادئة 0 أو 9 أو الكود الدولي)
                if not result and len(contact.phone_number) > 9:
                    short_phone = f"%{contact.phone_number[-9:]}"
                    cursor.execute(sql, (short_phone, search_start))
                    result = cursor.fetchone()
                
                if result:
                    logger.info(f"✅ تم العثور على سجل CDR للرقم {contact.phone_number}: {result}")
                    
                    # تحديث مدة المكالمة
                    contact.duration = result['billsec'] if result['billsec'] is not None else 0
                    
                    # تحديث الحالة بناءً على disposition
                    disposition = result['disposition']
                    if disposition == 'ANSWERED':
                        contact.status = 'answered'
                    elif disposition in ['BUSY', 'FAILED', 'NO ANSWER', 'CONGESTION']:
                        if contact.retries < settings.max_retries:
                            contact.retries += 1
                            contact.status = 'retry'
                            logger.info(f"🔄 جدولة إعادة محاولة للرقم {contact.phone_number} (المحاولة {contact.retries})")
                        else:
                            contact.status = 'failed'
                            logger.info(f"❌ فشل الاتصال بالرقم {contact.phone_number} بعد استنفاد المحاولات.")
                    else:
                        # حالات أخرى غير معروفة، نعتبرها فشل
                        contact.status = 'failed'
                        logger.warning(f"⚠️ حالة غير معروفة {disposition} للرقم {contact.phone_number}")

                    # حفظ التغييرات فوراً
                    session.add(contact)
                    session.commit()

                    # --- إرسال تنبيه تليجرام ---
                    if settings.telegram_bot_token and settings.telegram_chat_id and settings.telegram_notify_each_call:
                        if contact.status in ['answered', 'failed']:
                            campaign_name = contact.campaign.name if contact.campaign else "غير معروف"
                            msg = notifications.format_single_call_message(
                                contact.name, contact.phone_number, contact.status, contact.duration, campaign_name
                            )
                            notifications.send_telegram_message(settings.telegram_bot_token, settings.telegram_chat_id, msg)
                    # ---------------------------
                else:
                    # لم يتم العثور على سجل CDR
                    # logger.debug(f"لم يتم العثور على CDR للرقم {contact.phone_number}")
                    
                    # إذا مر وقت طويل جداً (ساعتين) ولم نجد سجل، نعتبرها failed
                    if (datetime.now() - contact.last_dialed).total_seconds() > 7200:
                         contact.status = 'failed'
                         session.commit()
                         logger.warning(f"⏰ انتهاء وقت انتظار CDR للرقم {contact.phone_number}. تم تعيين الحالة: failed")
        
        conn.close()
            
    except Exception as e:
        logger.error(f"❌ خطأ أثناء مزامنة CDR: {e}")

def revert_contact_status(contact_id, status='pending'):
    """
    إعادة تعيين حالة جهة الاتصال في حال فشل المهمة
    """
    session = Session()
    try:
        contact = session.query(Contact).get(contact_id)
        if contact:
            contact.status = status
            session.commit()
            logger.info(f"تم إعادة تعيين حالة الرقم {contact.phone_number} إلى {status} بسبب فشل المهمة")
    except Exception as e:
        logger.error(f"خطأ أثناء إعادة تعيين حالة جهة الاتصال: {e}")
        session.rollback()
    finally:
        session.close()

def dial_task(contact_id, phone_number, dongle_id, settings_dict):
    """
    مهمة الاتصال التي يتم تنفيذها في خيط منفصل (Thread)
    """
    try:
        # انتظار الفاصل الزمني (محاكاة delay)
        # هذا الانتظار يكون داخل الخيط، لذا لا يعطل الخيوط الأخرى
        delay = settings_dict.get('dial_delay', 5)
        if delay > 0:
            logger.info(f"الخيط: انتظار {delay} ثواني قبل الاتصال بالرقم {phone_number} عبر {dongle_id}")
            time.sleep(delay)

        # إنشاء اتصال AMI جديد لهذا الخيط
        ami = SimpleAMI(
            settings_dict['ami_host'],
            settings_dict['ami_port'],
            settings_dict['ami_user'],
            settings_dict['ami_secret']
        )
        
        # محاولة الاتصال بـ AMI
        if not ami.connect():
            logger.error(f"فشل الاتصال بـ AMI في الخيط للدونجل {dongle_id}")
            revert_contact_status(contact_id, 'pending')
            return

        # إجراء الاتصال
        channel = f"Dongle/{dongle_id}/{phone_number}"
        logger.info(f"الخيط: جاري بدء الاتصال بالرقم {phone_number} عبر {dongle_id}")
        
        # إشعار ببدء المكالمة
        notify_server('call_started', {'dongle': dongle_id, 'phone': phone_number})
        
        success = ami.originate_call(
            channel=channel,
            exten=settings_dict.get('target_queue', '501'), # Use target_queue from settings_dict (which now comes from Campaign)
            context='from-internal',
            priority=1,
            caller_id=f"Wasel<{phone_number}>"
        )
        
        if not success:
            logger.warning(f"فشل إرسال أمر Originate للرقم {phone_number} عبر {dongle_id}")
            revert_contact_status(contact_id, 'pending') # إعادة تعيين لتمكين إعادة المحاولة
            
    except Exception as e:
        logger.error(f"خطأ غير متوقع في مهمة الاتصال للرقم {phone_number}: {e}")
        revert_contact_status(contact_id, 'pending')

def run_dialer():
    logger.info("=== بدء تشغيل واصل - Wasel Auto Dialer (Ver 1.3 - Multi-Threaded) ===")
    
    last_cdr_sync = datetime.now()
    last_progress_notification = datetime.now()
    
    # مجمع الخيوط (Thread Pool) لإدارة الاتصالات المتوازية
    # سيتم تحديث عدد الخيوط بناءً على الإعدادات
    executor = None
    current_max_workers = 0
    
    # مجموعة لتتبع الدونجل المحجوزة حالياً من قبل الخيوط
    allocated_dongles = set()
    
    while True:
        session = Session()
        try:
            # 1. جلب الإعدادات
            settings = session.query(Settings).first()
            if not settings:
                logger.warning("لا توجد إعدادات في قاعدة البيانات. انتظار 10 ثواني...")
                time.sleep(10)
                continue
            
            # تحديث مجمع الخيوط إذا تغيرت الإعدادات
            target_workers = getattr(settings, 'concurrent_channels', 1)
            # نتأكد أن القيمة صالحة (على الأقل 1)
            if target_workers < 1: target_workers = 1
            
            if executor is None or current_max_workers != target_workers:
                logger.info(f"تحديث مجمع الخيوط إلى {target_workers} عامل...")
                # إذا كان هناك executor قديم، نتركه ينهي أعماله ببطء (أو يمكننا إغلاقه إذا أردنا)
                # ولكن للأمان، سننشئ واحد جديد. 
                # ملاحظة: ThreadPoolExecutor لا يدعم تغيير max_workers ديناميكياً بسهولة في الإصدارات القديمة
                if executor:
                    executor.shutdown(wait=False)
                executor = ThreadPoolExecutor(max_workers=target_workers)
                current_max_workers = target_workers

            # تحويل الإعدادات لقاموس لتمريره للخيوط بأمان
            settings_dict = {
                'ami_host': settings.ami_host,
                'ami_port': settings.ami_port,
                'ami_user': settings.ami_user,
                'ami_secret': settings.ami_secret,
                'dial_delay': settings.dial_delay,
                # 'target_queue': settings.target_queue # Removed, now per campaign
            }

            # --- مزامنة CDR كل دقيقة ---
            if (datetime.now() - last_cdr_sync).total_seconds() > 60:
                logger.info("بدء مزامنة سجلات CDR...")
                sync_cdr_data(session, settings)
                last_cdr_sync = datetime.now()

            # 2. البحث عن حملات نشطة (تعديل لدعم تعدد الحملات)
            active_campaigns = session.query(Campaign).filter_by(status='active').all()
            if not active_campaigns:
                logger.info("لا توجد حملات نشطة حالياً. انتظار 5 ثواني...")
                time.sleep(5)
                continue

            # 3. الاتصال بـ AMI وفحص الدونجل المتاحة (مرة واحدة للكل)
            ami = SimpleAMI(settings.ami_host, settings.ami_port, settings.ami_user, settings.ami_secret)
            if ami.connect():
                all_free_dongles = ami.get_free_dongles()
                
                # إشعار بحالة الدونجل
                notify_server('dongle_update', {'free': all_free_dongles, 'allocated': list(allocated_dongles)})
                
                # استبعاد الدونجل المحجوزة حالياً
                available_dongles = [d for d in all_free_dongles if d not in allocated_dongles]
                
                if not available_dongles:
                     # logger.debug("لا توجد دونجل متاحة حالياً.")
                     time.sleep(1)
                     continue

                logger.info(f"الدونجل المتاحة للعمل: {available_dongles}")
                
                # توزيع الدونجل على الحملات النشطة
                campaigns_count = len(active_campaigns)
                dongles_per_campaign = max(1, len(available_dongles) // campaigns_count)
                
                dongle_cursor = 0
                
                for i, active_campaign in enumerate(active_campaigns):
                    # تحديد حصة هذه الحملة من الدونجل
                    if i == campaigns_count - 1:
                        # الحملة الأخيرة تأخذ الباقي
                        my_dongles = available_dongles[dongle_cursor:]
                    else:
                        my_dongles = available_dongles[dongle_cursor : dongle_cursor + dongles_per_campaign]
                    
                    dongle_cursor += len(my_dongles)
                    
                    if not my_dongles:
                        continue

                    # --- تحديث التقدم عبر تليجرام ---
                    if settings.telegram_bot_token and settings.telegram_chat_id and settings.telegram_notify_progress:
                        now = datetime.now()
                        interval = timedelta(minutes=settings.telegram_notify_interval)
                        # استخدام وقت عام للتنبيه لتجنب الإغراق، أو يمكن تحسينه ليكون لكل حملة
                        if now - last_progress_notification > interval:
                            total = session.query(Contact).filter_by(campaign_id=active_campaign.id).count()
                            pending = session.query(Contact).filter_by(campaign_id=active_campaign.id, status='pending').count()
                            
                            if pending > 0:
                                dialed = session.query(Contact).filter_by(campaign_id=active_campaign.id, status='dialed').count()
                                answered = session.query(Contact).filter_by(campaign_id=active_campaign.id, status='answered').count()
                                
                                msg = notifications.format_progress_message(active_campaign.name, total, pending, dialed, answered)
                                if notifications.send_telegram_message(settings.telegram_bot_token, settings.telegram_chat_id, msg):
                                    last_progress_notification = now

                    # 4. جلب جهات اتصال لهذه الحملة
                    retry_threshold = datetime.now() - timedelta(seconds=settings.retry_interval)
                    
                    contacts = session.query(Contact).filter(
                        Contact.campaign_id == active_campaign.id,
                        or_(
                            Contact.status == 'pending',
                            and_(
                                Contact.status == 'retry',
                                Contact.last_dialed <= retry_threshold
                            )
                        )
                    ).order_by(Contact.retries.asc(), Contact.id.asc()).limit(len(my_dongles)).all()

                    if not contacts:
                        # التحقق من الانتهاء
                        pending_count = session.query(Contact).filter(
                            Contact.campaign_id == active_campaign.id,
                            or_(Contact.status == 'pending', Contact.status == 'retry')
                        ).count()
                        
                        dialed_count = session.query(Contact).filter_by(
                            campaign_id=active_campaign.id, status='dialed'
                        ).count()

                        if pending_count == 0 and dialed_count == 0:
                             logger.info(f"الحملة '{active_campaign.name}' انتهت.")
                             active_campaign.status = 'completed'
                             session.commit()
                             
                             if settings.telegram_bot_token and settings.telegram_chat_id and settings.telegram_notify_start_stop:
                                 msg = notifications.format_campaign_status_message(active_campaign.name, 'completed', "تم الانتهاء من جميع الأرقام في الحملة.")
                                 notifications.send_telegram_message(settings.telegram_bot_token, settings.telegram_chat_id, msg)
                    else:
                        # توزيع المهام على الخيوط
                        valid_contacts_to_dial = []
                        for contact in contacts:
                            is_blacklisted = session.query(Blacklist).filter_by(phone_number=contact.phone_number).first()
                            if is_blacklisted:
                                logger.warning(f"تم تخطي الرقم {contact.phone_number} لأنه موجود في القائمة السوداء.")
                                contact.status = 'failed'
                                contact.last_dialed = datetime.now()
                                session.commit()
                            else:
                                valid_contacts_to_dial.append(contact)
                        
                        for idx, contact in enumerate(valid_contacts_to_dial):
                            if idx < len(my_dongles):
                                dongle_id = my_dongles[idx]
                                
                                allocated_dongles.add(dongle_id)
                                
                                contact.status = 'dialed'
                                contact.last_dialed = datetime.now()
                                session.commit()
                                
                                logger.info(f"تخصيص الدونجل {dongle_id} للرقم {contact.phone_number} (حملة: {active_campaign.name})")
                                
                                task_settings = settings_dict.copy()
                                task_settings['target_queue'] = active_campaign.target_queue
                                
                                future = executor.submit(dial_task, contact.id, contact.phone_number, dongle_id, task_settings)
                                
                                def on_task_done(f, d=dongle_id):
                                    allocated_dongles.discard(d)
                                    notify_server('call_ended', {'dongle': d})
                                
                                future.add_done_callback(on_task_done)
                            
                else:
                    logger.info("لا توجد خطوط دونجل شاغرة حالياً (الكل مشغول أو محجوز).")
                    time.sleep(2)
            else:
                logger.error("فشل الاتصال بمدير النظام (AMI) في الحلقة الرئيسية.")
                time.sleep(10)

        except Exception as e:
            logger.exception(f"حدث خطأ غير متوقع في الحلقة الرئيسية: {e}")
            time.sleep(5)
        finally:
            session.close()

if __name__ == "__main__":
    run_dialer()
