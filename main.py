#!/usr/bin/env python3
"""
🔥 Telegram Multi-Account Report Bot for Authorized Pentesting
Supports: User/Channel/Group/Bot Reports with 10+ Categories
Database: SQLite with full history & stats
Author: HackerAI - Authorized Pentest Tool
"""

import asyncio
import logging
import json
import os
import re
import sqlite3
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat
from telethon.errors import SessionPasswordNeededError

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 🔥 REPORT CATEGORIES FOR PENTESTING
REPORT_CATEGORIES = {
    'porn': {'name': 'Porn/Adult', 'desc': 'NSFW, nudity', 'severity': 4},
    'spam': {'name': 'Spam', 'telegram_reason': 'spam', 'desc': 'Mass messaging', 'severity': 2},
    'leak': {'name': 'Data Leak', 'desc': 'Credentials, PII', 'severity': 5},
    'scam': {'name': 'Scam/Fraud', 'telegram_reason': 'scam', 'desc': 'Financial fraud', 'severity': 5},
    'violence': {'name': 'Violence', 'telegram_reason': 'violence', 'desc': 'Threats, extremism', 'severity': 5},
    'illegal': {'name': 'Illegal', 'desc': 'Drugs, weapons, hacking', 'severity': 5},
    'copyright': {'name': 'Copyright', 'telegram_reason': 'copyright', 'desc': 'Piracy', 'severity': 3},
    'fake': {'name': 'Impersonation', 'desc': 'Fake accounts', 'severity': 4},
    'botnet': {'name': 'Malicious Bot', 'desc': 'Spamming/malware bots', 'severity': 4},
    'phishing': {'name': 'Phishing', 'desc': 'Fake logins', 'severity': 5},
    'child': {'name': 'Child Abuse', 'telegram_reason': 'child_abuse', 'desc': 'CSAM', 'severity': 5},
    'fake_news': {'name': 'Fake News', 'desc': 'Misinformation', 'severity': 3}
}

CATEGORY_ALIASES = {
    'porno': 'porn', 'nsfw': 'porn', 'adult': 'porn', 'sex': 'porn',
    'spamming': 'spam', 'ads': 'spam', 'promotion': 'spam',
    'data_leak': 'leak', 'credentials': 'leak', 'dox': 'leak',
    'fraud': 'scam', 'crypto_scam': 'scam', 'investment': 'scam',
    'terror': 'violence', 'isis': 'violence', 'weapon': 'violence',
    'drugs': 'illegal', 'hack': 'illegal', 'card': 'illegal',
    'pirate': 'copyright', 'movie': 'copyright', 'crack': 'copyright',
    'impersonate': 'fake', 'fake_account': 'fake',
    'malware': 'botnet', 'virus': 'botnet',
    'phish': 'phishing', 'login': 'phishing'
}

class TelegramReportBot:
    def __init__(self):
        self.clients = {}
        self.session_dir = "sessions"
        self.db_path = "reports.db"
        self.config_file = "config.json"
        os.makedirs(self.session_dir, exist_ok=True)
        self.init_db()
        self.load_config()
    
    def init_db(self):
        """Initialize pentest database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_phone TEXT,
                reporter_id INTEGER,
                target_type TEXT,
                target_id INTEGER,
                target_username TEXT,
                target_title TEXT,
                category TEXT,
                reason TEXT,
                severity INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                date TEXT PRIMARY KEY,
                total_reports INTEGER DEFAULT 0,
                by_category TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def load_config(self):
        """Load saved accounts config"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.clients_config = config.get('accounts', [])
    
    def save_config(self):
        """Save accounts config"""
        config = {'accounts': self.clients_config}
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def detect_category(self, reason):
        """Smart category detection"""
        reason_lower = reason.lower()
        for alias, category in CATEGORY_ALIASES.items():
            if alias in reason_lower:
                return category
        for category, data in REPORT_CATEGORIES.items():
            if data.get('telegram_reason') and data['telegram_reason'] in reason_lower:
                return category
        return 'spam'
    
    def parse_report_command(self, text):
        """Parse advanced report commands"""
        # /report_user @target porn OR /report_user 123456 spam
        pattern = r'/report_(user|channel|group|bot)(?:\s+(.+?))?(?:\s+(.+))?/?i'
        match = re.match(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        cmd_type, target, raw_reason = match.groups()
        target = target.strip().lstrip('@') if target else None
        raw_reason = raw_reason.strip() if raw_reason else None
        
        if not target:
            return None
        
        category = self.detect_category(raw_reason or 'spam')
        full_reason = f"{REPORT_CATEGORIES[category]['name']}: {raw_reason or ''}".strip(': ')
        
        return {
            'type': cmd_type,
            'target': target,
            'category': category,
            'reason': full_reason,
            'severity': REPORT_CATEGORIES[category]['severity']
        }
    
    async def get_entity_info(self, client, target):
        """Get target details for pentest reporting"""
        try:
            entity = await client.get_entity(target)
            info = {}
            
            if isinstance(entity, User):
                info = {
                    'type': 'user',
                    'id': entity.id,
                    'username': entity.username,
                    'title': f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                }
            elif isinstance(entity, (Channel, Chat)):
                info = {
                    'type': 'channel' if hasattr(entity, 'megagroup') else 'group',
                    'id': entity.id,
                    'username': entity.username,
                    'title': entity.title
                }
            return info
        except Exception as e:
            logger.error(f"Entity lookup failed: {e}")
            return None
    
    async def create_report(self, client, parsed):
        """Create pentest report"""
        entity_info = await self.get_entity_info(client, parsed['target'])
        if not entity_info:
            return False
        
        me = await client.get_me()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO reports 
            (reporter_phone, reporter_id, target_type, target_id, target_username, 
             target_title, category, reason, severity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            me.phone or 'unknown',
            me.id,
            entity_info['type'],
            entity_info['id'],
            entity_info['username'] or '',
            entity_info['title'] or '',
            parsed['category'],
            parsed['reason'],
            parsed['severity']
        ))
        
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Report #{report_id} created: {parsed['target']} ({parsed['category']})")
        return report_id
    
    async def bulk_report(self, client, targets, category='spam'):
        """Bulk report multiple targets"""
        results = []
        for target in targets:
            parsed = {'type': 'user', 'target': target, 'category': category, 'reason': f"{category}", 'severity': 2}
            success = await self.create_report(client, parsed)
            results.append(success)
            await asyncio.sleep(1)  # Rate limit
        return results

# Global bot instance
bot = TelegramReportBot()

# 🔥 EVENT HANDLERS
@events.register(events.NewMessage(pattern='/start'))
async def start_handler(event):
    welcome = """
🔥 **AUTHORIZED PENTEST REPORT BOT** 🔥

**Commands:**
• `/report_user @target [porn/spam/leak]` 
• `/report_channel @channel scam`
• `/report_group -100123456 leak`
• `/report_bot @botname phishing`

**Quick Categories:** porn spam leak scam violence illegal copyright fake botnet phishing child

**Management:**
`/my_reports` `/stats` `/categories` `/accounts` `/bulk @list`

**Status: ACTIVE - Pentest Authorized**
    """
    await event.respond(welcome)

@events.register(events.NewMessage(pattern=r'/report_(user|channel|group|bot)'))
async def report_handler(event):
    parsed = bot.parse_report_command(event.raw_text)
    if not parsed:
        await event.respond("❌ **Usage:** `/report_user @target spam`\nType `/categories`")
        return
    
    report_id = await bot.create_report(event.client, parsed)
    emoji = "✅" if report_id else "❌"
    
    response = f"{emoji} **Report #{report_id}** *(Severity: {parsed['severity']}/5)*\n\n"
    response += f"🎯 **{parsed['type'].title()}:** `@{parsed['target']}`\n"
    response += f"🏷️ **Category:** `{parsed['category']}`\n"
    response += f"📝 **Reason:** {parsed['reason']}\n"
    response += f"💾 **Database:** Saved ✅"
    
    await event.respond(response)

@events.register(events.NewMessage(pattern='/categories'))
async def categories_handler(event):
    cats = "**📂 Report Categories (Severity 1-5):**\n\n"
    for code, data in REPORT_CATEGORIES.items():
        cats += f"• `{code}` **({data['severity']})** - {data['name']}\n"
        cats += f"  _{data['desc']}_\n\n"
    await event.respond(cats)

@events.register(events.NewMessage(pattern='/my_reports'))
async def my_reports_handler(event):
    me = await event.client.get_me()
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, target_type, target_username, category, severity, status, created_at 
        FROM reports WHERE reporter_id = ? ORDER BY created_at DESC LIMIT 15
    ''', (me.id,))
    reports = cursor.fetchall()
    conn.close()
    
    if not reports:
        await event.respond("No reports found.")
        return
    
    report_list = "**📋 Your Recent Reports:**\n\n"
    for r in reports:
        report_list += f"**#{r[0]}** `{r[1]}` `@{r[2]}` **{r[3]}**({r[4]})\n"
        report_list += f"_{r[5]}_ {r[6][:16]}\n\n"
    
    await event.respond(report_list)

@events.register(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
    conn = sqlite3.connect(bot.db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM reports')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT category, COUNT(*), AVG(severity) FROM reports GROUP BY category')
    breakdown = cursor.fetchall()
    conn.close()
    
    stats = f"**📊 Pentest Stats**\n**Total Reports:** `{total}`\n\n"
    for cat, count, avg_sev in breakdown:
        stats += f"• `{cat}`: **{count}** (Avg: {avg_sev:.1f})\n"
    await event.respond(stats)

@events.register(events.NewMessage(pattern='/bulk'))
async def bulk_handler(event):
    await event.respond("**Bulk reporting:** `/bulk user1 user2 user3 spam`\nComing soon in v2!")

async def setup_accounts():
    """Multi-account setup for pentesting"""
    print("🔥 TELEGRAM PENTEST BOT - AUTHORIZED SETUP")
    print("=" * 50)
    
    accounts = []
    while True:
        try:
            api_id = int(input("\nAPI ID (0 to skip): "))
            if api_id == 0:
                break
            
            api_hash = input("API Hash: ").strip()
            phone = input("Phone (+country): ").strip()
            
            session_name = f"{bot.session_dir}/{phone}"
            client = TelegramClient(session_name, api_id, api_hash)
            
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                code = input(f"Code for {phone}: ")
                
                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    password = input("2FA Password: ")
                    await client.sign_in(password=password)
            
            me = await client.get_me()
            accounts.append(client)
            print(f"✅ {me.phone or me.username} added ({len(accounts)} accounts)")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    if not accounts:
        print("No accounts. Exiting.")
        return []
    
    print(f"\n🚀 Starting {len(accounts)} clients...")
    return accounts

async def main():
    accounts = await setup_accounts()
    if not accounts:
        return
    
    # Add handlers to all clients
    handlers = [start_handler, report_handler, categories_handler, 
               my_reports_handler, stats_handler]
    
    for client in accounts:
        for handler in handlers:
            client.add_event_handler(handler)
        await client.start()
    
    print("✅ Bot running! Send commands to 'Saved Messages'")
    print("Press Ctrl+C to stop")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    finally:
        for client in accounts:
            await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
