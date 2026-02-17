import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat
import json
import os
from datetime import datetime
import sqlite3

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramReportBot:
    def __init__(self):
        self.clients = {}
        self.session_dir = "sessions"
        self.db_path = "reports.db"
        self.init_db()
        os.makedirs(self.session_dir, exist_ok=True)
        
    def init_db(self):
        """Initialize SQLite database for reports"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER,
                target_type TEXT,
                target_id INTEGER,
                target_username TEXT,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    async def add_account(self, api_id, api_hash, phone):
        """Add new Telegram account"""
        session_name = f"{self.session_dir}/{phone}"
        client = TelegramClient(session_name, api_id, api_hash)
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            code = input(f"Enter code for {phone}: ")
            await client.sign_in(phone, code)
        
        self.clients[phone] = client
        logger.info(f"Account {phone} added successfully")
        return client
    
    async def get_entity_info(self, client, target):
        """Get detailed info about target"""
        try:
            entity = await client.get_entity(target)
            if isinstance(entity, User):
                return {
                    'type': 'user',
                    'id': entity.id,
                    'username': entity.username,
                    'first_name': entity.first_name,
                    'last_name': entity.last_name or '',
                    'phone': getattr(entity, 'phone', None)
                }
            elif isinstance(entity, (Channel, Chat)):
                return {
                    'type': 'channel' if isinstance(entity, Channel) else 'group',
                    'id': entity.id,
                    'username': entity.username,
                    'title': entity.title
                }
        except Exception as e:
            logger.error(f"Error getting entity info: {e}")
            return None
    
    async def report_target(self, client, target, reason):
        """Create report in database"""
        entity_info = await self.get_entity_info(client, target)
        if not entity_info:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reports (reporter_id, target_type, target_id, target_username, reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            (await client.get_me()).id,
            entity_info['type'],
            entity_info['id'],
            entity_info['username'] or '',
            reason
        ))
        conn.commit()
        conn.close()
        return True
    
    @staticmethod
    async def show_menu(client):
        """Show main menu"""
        menu = """
🔥 **REPORT BOT MENU** 🔥

📋 **Commands:**
• `/report_user @username` or `user_id` - Report User
• `/report_channel @channel` - Report Channel  
• `/report_group @group` - Report Group
• `/report_bot @bot` - Report Bot
• `/my_reports` - View your reports
• `/stats` - View stats
• `/accounts` - Manage accounts
• `/help` - Show this menu

**Usage Example:**
`/report_user @spammer123 Spam and harassment`
        """
        await client.send_message('me', menu)

# Bot instance
bot = TelegramReportBot()

@events.register(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await bot.show_menu(event.client)

@events.register(events.NewMessage(pattern=r'/report_user(?:\s+(.+))?'))
async def report_user_handler(event):
    if not event.raw_text.split(' ', 2)[1:]:
        await event.respond("Usage: `/report_user @username or user_id REASON`")
        return
    
    parts = event.raw_text.split(' ', 2)
    target = parts[1].strip().replace('@', '')
    reason = parts[2] if len(parts) > 2 else "Spam"
    
    success = await bot.report_target(event.client, target, reason)
    status = "✅ Report created successfully!" if success else "❌ Failed to create report"
    await event.respond(status)

@events.register(events.NewMessage(pattern=r'/report_channel(?:\s+(.+))?'))
async def report_channel_handler(event):
    if not event.raw_text.split(' ', 2)[1:]:
        await event.respond("Usage: `/report_channel @channel REASON`")
        return
    
    parts = event.raw_text.split(' ', 2)
    target = parts[1].strip().replace('@', '')
    reason = parts[2] if len(parts) > 2 else "Violates ToS"
    
    success = await bot.report_target(event.client, target, reason)
    status = "✅ Channel report created!" if success else "❌ Failed to report channel"
    await event.respond(status)

@events.register(events.NewMessage(pattern=r'/report_group(?:\s+(.+))?'))
async def report_group_handler(event):
    if not event.raw_text.split(' ', 2)[1:]:
        await event.respond("Usage: `/report_group @group REASON`")
        return
    
    parts = event.raw_text.split(' ', 2)
    target = parts[1].strip().replace('@', '')
    reason = parts[2] if len(parts) > 2 else "Illegal content"
    
    success = await bot.report_target(event.client, target, reason)
    status = "✅ Group report created!" if success else "❌ Failed to report group"
    await event.respond(status)

@events.register(events.NewMessage(pattern=r'/report_bot(?:\s+(.+))?'))
async def report_bot_handler(event):
    if not event.raw_text.split(' ', 2)[1:]:
        await event.respond("Usage: `/report_bot @botusername REASON`")
        return
    
    parts = event.raw_text.split(' ', 2)
    target = parts[1].strip().replace('@', '')
    reason = parts[2] if len(parts) > 2 else "Malicious bot"
    
    success = await bot.report_target(event.client, target, reason)
    status = "✅ Bot report created!" if success else "❌ Failed to report bot"
    await event.respond(status)

@events.register(events.NewMessage(pattern='/my_reports'))
async def my_reports_handler(event):
    me = await event.client.get_me()
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT target_type, target_username, reason, status, created_at 
        FROM reports WHERE reporter_id = ? ORDER BY created_at DESC LIMIT 10
    ''', (me.id,))
    
    reports = cursor.fetchall()
    conn.close()
    
    if not reports:
        await event.respond("No reports found.")
        return
    
    report_list = "📋 **Your Recent Reports:**\n\n"
    for report in reports:
        report_list += f"• **{report[0].title()}**: @{report[1] or 'N/A'}\n"
        report_list += f"  Reason: {report[2]}\n"
        report_list += f"  Status: {report[3]}\n"
        report_list += f"  Date: {report[4][:16]}\n\n"
    
    await event.respond(report_list)

@events.register(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM reports')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT target_type, COUNT(*) FROM reports GROUP BY target_type')
    breakdown = cursor.fetchall()
    conn.close()
    
    stats = f"📊 **Report Stats**\n\nTotal Reports: **{total}**\n\n"
    for typ, count in breakdown:
        stats += f"• {typ.title()}: **{count}**\n"
    
    await event.respond(stats)

async def main():
    print("🔥 Telegram Report Bot Starting...")
    print("Enter your API credentials:")
    
    # Multi-account setup
    accounts = []
    while True:
        api_id = int(input("API ID (or 0 to skip): "))
        if api_id == 0:
            break
        api_hash = input("API Hash: ")
        phone = input("Phone number (+1234567890): ")
        client = await bot.add_account(api_id, api_hash, phone)
        accounts.append(client)
    
    if not accounts:
        print("No accounts added. Exiting.")
        return
    
    print("Bot is running... Press Ctrl+C to stop")
    
    # Register handlers for all clients
    for client in accounts:
        client.add_event_handler(start_handler)
        client.add_event_handler(report_user_handler)
        client.add_event_handler(report_channel_handler)
        client.add_event_handler(report_group_handler)
        client.add_event_handler(report_bot_handler)
        client.add_event_handler(my_reports_handler)
        client.add_event_handler(stats_handler)
    
    # Start all clients
    await asyncio.gather(*(client.start() for client in accounts))
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
