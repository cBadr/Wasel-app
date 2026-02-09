import requests
import logging

logger = logging.getLogger(__name__)

def send_telegram_message(token, chat_id, message):
    """
    Send message via Telegram
    """
    if not token or not chat_id:
        logger.warning("Telegram token or chat_id is missing. Notification skipped.")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info("Telegram notification sent successfully.")
            return True
        else:
            logger.error(f"Failed to send Telegram notification: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception while sending Telegram notification: {e}")
        return False

def format_campaign_status_message(campaign_name, status, details=None):
    """
    Format campaign status message (Enthusiastic English)
    """
    if status == 'active':
        icon = "🚀"
        header = "CAMPAIGN STARTED!"
        status_text = "LIVE & BLASTING ⚡"
        intro = f"The campaign *{campaign_name}* is now **LIVE**! Let's get some results! 💪"
    elif status == 'paused':
        icon = "⏸"
        header = "CAMPAIGN PAUSED"
        status_text = "ON BREAK ⏳"
        intro = f"The campaign *{campaign_name}* is currently on hold. Ready to resume whenever you are!"
    else:
        icon = "🎉"
        header = "CAMPAIGN COMPLETED!"
        status_text = "MISSION ACCOMPLISHED 🏆"
        intro = f"Great news! The campaign *{campaign_name}* has finished all calls! Time to celebrate! 🥳"
    
    msg = f"{icon} *{header}*\n\n"
    msg += f"{intro}\n\n"
    msg += f"📋 *Campaign:* `{campaign_name}`\n"
    msg += f"📊 *Status:* {status_text}\n"
    
    if details:
        msg += f"\n📝 *Note:* {details}"
        
    msg += "\n\n_Powered by Wasel Auto Dialer_ 🚀"
    return msg

def format_progress_message(campaign_name, total, pending, dialed, answered):
    """
    Format progress message (Enthusiastic English)
    """
    percent = 0
    if total > 0:
        percent = round(((total - pending) / total) * 100, 1)
        
    msg = f"📈 *PERFORMANCE UPDATE* 🚀\n\n"
    msg += f"Here is the latest scoop on *{campaign_name}*:\n\n"
    msg += f"🔥 *Progress:* `{percent}%`\n"
    msg += f"📞 *Dialed:* `{dialed}`\n"
    msg += f"✅ *Answered:* `{answered}`\n"
    msg += f"⏳ *Remaining:* `{pending}`\n"
    msg += f"🔢 *Total Targets:* `{total}`\n\n"
    
    msg += "Keep the momentum going! 💪\n"
    msg += "_Powered by Wasel Auto Dialer_"
    return msg

def format_single_call_message(contact_name, phone_number, status, duration, campaign_name):
    """
    Format single call message (Enthusiastic English)
    """
    if status == 'answered':
        icon = "✅"
        header = "SUCCESSFUL CONNECTION!"
        status_text = "ANSWERED"
        duration_text = f"⏱ *Duration:* `{duration}s`"
    else:
        icon = "❌"
        header = "MISSED OPPORTUNITY"
        status_text = "FAILED / NO ANSWER"
        duration_text = ""
    
    msg = f"🔔 *{header}* {icon}\n\n"
    msg += f"👤 *Client:* {contact_name or 'Unknown'}\n"
    msg += f"📱 *Phone:* `{phone_number}`\n\n"
    msg += f"📊 *Status:* {status_text}\n"
    
    if duration_text:
        msg += f"{duration_text}\n"
        
    msg += f"🎯 *Campaign:* {campaign_name}\n\n"
    msg += "_Another step towards success!_ 🚀"
    return msg
