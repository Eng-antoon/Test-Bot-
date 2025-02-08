# db.py
import sqlite3
import json
from config import DATABASE

def get_connection():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER,
            role TEXT,
            bot TEXT,
            phone TEXT,
            client TEXT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            chat_id INTEGER,
            PRIMARY KEY (user_id, bot)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            issue_description TEXT,
            issue_type TEXT,
            client TEXT,
            image_url TEXT,
            status TEXT,
            da_id INTEGER,
            logs TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_subscription(user_id, phone, role, bot, client, username, first_name, last_name, chat_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO subscriptions 
        (user_id, role, bot, phone, client, username, first_name, last_name, chat_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, role, bot, phone, client, username, first_name, last_name, chat_id))
    conn.commit()
    conn.close()

def get_subscription(user_id, bot):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE user_id=? AND bot=?", (user_id, bot))
    sub = c.fetchone()
    conn.close()
    return sub

def get_all_subscriptions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions")
    subs = c.fetchall()
    conn.close()
    return subs

def add_ticket(order_id, issue_description, issue_type, client, image_url, status, da_id):
    logs = json.dumps([{"action": "ticket_created", "by": da_id}])
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO tickets 
        (order_id, issue_description, issue_type, client, image_url, status, da_id, logs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, issue_description, issue_type, client, image_url, status, da_id, logs))
    ticket_id = c.lastrowid
    conn.commit()
    conn.close()
    return ticket_id

def get_ticket(ticket_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,))
    ticket = c.fetchone()
    conn.close()
    return ticket

def get_all_tickets():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM tickets")
    tickets = c.fetchall()
    conn.close()
    return tickets

def update_ticket_status(ticket_id, new_status, log_entry):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT logs FROM tickets WHERE ticket_id=?", (ticket_id,))
    row = c.fetchone()
    logs = []
    if row and row["logs"]:
        logs = json.loads(row["logs"])
    logs.append(log_entry)
    logs_str = json.dumps(logs)
    c.execute("UPDATE tickets SET status=?, logs=? WHERE ticket_id=?", (new_status, logs_str, ticket_id))
    conn.commit()
    conn.close()

def search_tickets_by_order(order_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM tickets WHERE order_id LIKE ?", ('%' + order_id + '%',))
    tickets = c.fetchall()
    conn.close()
    return tickets

def get_all_open_tickets():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM tickets 
        WHERE status IN ('Opened', 'Pending DA Response', 'Awaiting Client Response', 'Awaiting Supervisor Approval', 'Client Responded', 'Client Ignored')
    """)
    tickets = c.fetchall()
    conn.close()
    return tickets

def get_supervisors():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE role='Supervisor'")
    supervisors = c.fetchall()
    conn.close()
    return supervisors

def get_clients_by_name(client_name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE role='Client' AND client=?", (client_name,))
    clients = c.fetchall()
    conn.close()
    return clients
