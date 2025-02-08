# webapp.py
from flask import Flask, render_template_string, request
import db
import json

app = Flask(__name__)

TICKETS_TEMPLATE = """
<!doctype html>
<title>Tickets</title>
<h1>Tickets</h1>
<table border=1>
  <tr>
    <th>ID</th>
    <th>Order ID</th>
    <th>Description</th>
    <th>Type</th>
    <th>Client</th>
    <th>Status</th>
    <th>DA ID</th>
    <th>Created At</th>
    <th>النشاط</th>
  </tr>
  {% for t in tickets %}
  <tr>
    <td>{{ t['ticket_id'] }}</td>
    <td>{{ t['order_id'] }}</td>
    <td>{{ t['issue_description'] }}</td>
    <td>{{ t['issue_type'] }}</td>
    <td>{{ t['client'] }}</td>
    <td>{{ t['status'] }}</td>
    <td>{{ t['da_id'] }}</td>
    <td>{{ t['created_at'] }}</td>
    <td><a href="/ticket/{{ t['ticket_id'] }}/activity">عرض النشاط</a></td>
  </tr>
  {% endfor %}
</table>
<a href="/">Back to Home</a>
"""

SUBSCRIPTIONS_TEMPLATE = """
<!doctype html>
<title>Subscriptions</title>
<h1>Subscriptions</h1>
<table border=1>
  <tr>
    <th>User ID</th>
    <th>Role</th>
    <th>Bot</th>
    <th>Phone</th>
    <th>Client</th>
    <th>Username</th>
    <th>First Name</th>
    <th>Last Name</th>
    <th>Chat ID</th>
  </tr>
  {% for u in subs %}
  <tr>
    <td>{{ u['user_id'] }}</td>
    <td>{{ u['role'] }}</td>
    <td>{{ u['bot'] }}</td>
    <td>{{ u['phone'] }}</td>
    <td>{{ u['client'] }}</td>
    <td>{{ u['username'] }}</td>
    <td>{{ u['first_name'] }}</td>
    <td>{{ u['last_name'] }}</td>
    <td>{{ u['chat_id'] }}</td>
  </tr>
  {% endfor %}
</table>
<a href="/">Back to Home</a>
"""

HOME_TEMPLATE = """
<!doctype html>
<title>Issue Resolution Admin</title>
<h1>Issue Resolution Admin</h1>
<ul>
  <li><a href="/tickets">View All Tickets</a></li>
  <li><a href="/subscriptions">View Subscriptions</a></li>
</ul>
"""

ACTIVITY_TEMPLATE = """
<!doctype html>
<title>Ticket Activity</title>
<h1>Activity for Ticket #{{ ticket_id }}</h1>
<pre>
{{ logs }}
</pre>
<a href="/tickets">Back to Tickets</a>
"""

@app.route("/")
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route("/tickets")
def tickets():
    tickets = db.get_all_tickets()
    return render_template_string(TICKETS_TEMPLATE, tickets=tickets)

@app.route("/ticket/<int:ticket_id>/activity")
def ticket_activity(ticket_id):
    t = db.get_ticket(ticket_id)
    if not t:
        return "Ticket not found", 404
    logs = json.dumps(json.loads(t['logs']), ensure_ascii=False, indent=2)
    return render_template_string(ACTIVITY_TEMPLATE, ticket_id=ticket_id, logs=logs)

@app.route("/subscriptions")
def subscriptions():
    subs = db.get_all_subscriptions()
    return render_template_string(SUBSCRIPTIONS_TEMPLATE, subs=subs)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
