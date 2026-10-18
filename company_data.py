"""Sample company 'Nimbus Labs' for the Company Brain (Track 03).

Structured facts (people, teams, systems, ownership) + unstructured knowledge
(docs, tickets, chats) + decisions with provenance and a supersede chain.
"""

TEAMS = ["Platform", "Product", "Security", "Data", "Support"]

PEOPLE = [
    ("Priya Nair", "CTO", "Platform"),
    ("Sana Khan", "Backend Lead", "Platform"),
    ("Rohan Gupta", "Backend Engineer", "Platform"),
    ("Aarav Joshi", "Backend Engineer", "Platform"),
    ("Karan Singh", "Site Reliability Engineer", "Platform"),
    ("Meera Iyer", "Frontend Lead", "Product"),
    ("Neha Verma", "Product Manager", "Product"),
    ("Dev Patel", "Security Engineer", "Security"),
    ("Ishita Rao", "Data Engineer", "Data"),
    ("Imran Ali", "Support Lead", "Support"),
]

SYSTEMS = [
    ("Auth Service", "Logins, sessions and SSO"),
    ("Payments API", "Charges, refunds and settlements"),
    ("Notification Service", "Email and push delivery"),
    ("Postgres Primary", "Main relational database"),
    ("Kafka Event Bus", "Event streaming between services"),
    ("Web App", "Customer web application"),
    ("Mobile App", "Customer mobile application"),
    ("Analytics Pipeline", "Event ingestion into the warehouse"),
]

# (system, depends_on)
DEPENDS_ON = [
    ("Web App", "Auth Service"), ("Web App", "Payments API"), ("Web App", "Notification Service"),
    ("Mobile App", "Auth Service"), ("Mobile App", "Payments API"),
    ("Payments API", "Postgres Primary"), ("Payments API", "Kafka Event Bus"),
    ("Auth Service", "Postgres Primary"),
    ("Notification Service", "Kafka Event Bus"),
    ("Analytics Pipeline", "Kafka Event Bus"), ("Analytics Pipeline", "Postgres Primary"),
]

# (owner, system, since, until)  - owner may be a person or a team
OWNS = [
    ("Sana Khan", "Payments API", "2026-01-15", None),
    ("Karan Singh", "Postgres Primary", "2026-01-15", None),
    ("Karan Singh", "Kafka Event Bus", "2026-01-15", None),
    ("Security", "Auth Service", "2026-01-15", None),
    ("Meera Iyer", "Web App", "2026-01-15", None),
    ("Meera Iyer", "Mobile App", "2026-01-15", None),
    ("Ishita Rao", "Analytics Pipeline", "2026-01-15", None),
    ("Rohan Gupta", "Notification Service", "2026-07-10", "2026-09-30"),
    ("Aarav Joshi", "Notification Service", "2026-09-30", None),
]

# (name, description, status, leader, systems)
PROJECTS = [
    ("Atlas", "Payments migration to Razorpay", "active", "Sana Khan", ["Payments API"]),
    ("Beacon", "Notification revamp with push", "active", "Neha Verma",
     ["Notification Service", "Web App", "Mobile App"]),
    ("Shield", "SSO and security hardening", "active", "Dev Patel", ["Auth Service", "Web App"]),
    ("Lumen", "Analytics pipeline", "active", "Ishita Rao", ["Analytics Pipeline", "Kafka Event Bus"]),
]

# Words that should link a text to a system even if the exact name isn't used
ALIASES = {
    "Kafka Event Bus": ["event bus", "kafka"],
    "Postgres Primary": ["postgres"],
    "Payments API": ["payments"],
    "Auth Service": ["sso"],
}

SOURCES = [
    # ---------------------------------------------------------------- docs
    dict(id="DOC-101", type="doc", title="Payments Provider Evaluation", author="Sana Khan",
         date="2026-02-18", project="Atlas",
         text="We compared Stripe and Razorpay for the Payments API. Stripe wins on speed to launch because our "
              "checkout already integrates with it. Razorpay has better INR settlement but needs a rebuild of the "
              "Payments API client. Recommendation: start with Stripe and revisit if settlement costs hurt."),
    dict(id="DOC-102", type="doc", title="RFC: Idempotent Payment Webhooks", author="Rohan Gupta",
         date="2026-03-05", project="Atlas",
         text="Payment webhooks will be published to the Kafka Event Bus and consumed idempotently by the "
              "Payments API. Duplicate events are dropped using the event id stored in Postgres Primary."),
    dict(id="DOC-103", type="doc", title="Razorpay Migration Plan", author="Sana Khan",
         date="2026-08-12", project="Atlas",
         text="Stripe settlements in INR take 5 to 7 days and add FX fees. We will migrate the Payments API to "
              "Razorpay for Indian customers and keep Stripe only for international customers until Q1. This "
              "replaces the Stripe-first plan in DOC-101. Rohan Gupta builds the new client and Karan Singh "
              "reviews the load on Postgres Primary."),
    dict(id="DOC-104", type="doc", title="Auth Service Threat Model", author="Dev Patel",
         date="2026-05-20", project="Shield",
         text="Auth Service stores session tokens in Postgres Primary and signs them with a long-lived key. Main "
              "risks are key leakage and password reuse. Recommendation: adopt SSO and rotate signing keys every "
              "90 days."),
    dict(id="DOC-105", type="doc", title="SSO Rollout Decision", author="Priya Nair",
         date="2026-06-02", project="Shield",
         text="Based on the Auth Service threat model in DOC-104, we will adopt Okta for company-wide SSO, "
              "starting with the Web App. Dev Patel leads the rollout."),
    dict(id="DOC-106", type="doc", title="Notification Revamp PRD", author="Neha Verma",
         date="2026-07-10", project="Beacon",
         text="Beacon adds push notifications alongside email. The Notification Service consumes events from the "
              "Kafka Event Bus and delivers to the Web App and Mobile App. Target launch: October."),
    dict(id="DOC-107", type="doc", title="Postgres Failover Runbook", author="Karan Singh",
         date="2026-04-14", project=None,
         text="If Postgres Primary fails, promote the replica within 5 minutes. Auth Service and Payments API are "
              "down or read-only until promotion completes. Page Karan Singh first, then Sana Khan."),
    dict(id="DOC-108", type="doc", title="Analytics Pipeline Design", author="Ishita Rao",
         date="2026-07-25", project="Lumen",
         text="Lumen streams events from the Kafka Event Bus into the warehouse. The Analytics Pipeline reads user "
              "events and payment events. Ishita Rao owns the pipeline and Karan Singh owns consumer scaling."),
    # ---------------------------------------------------------------- tickets
    dict(id="TKT-201", type="ticket", title="Payments timeouts on settlement", author=None, assignee="Rohan Gupta",
         date="2026-08-20", project="Atlas",
         text="Settlement calls from the Payments API time out under load. Suspect slow queries on Postgres "
              "Primary. Status: open."),
    dict(id="TKT-202", type="ticket", title="Rotate Auth signing keys", author=None, assignee="Dev Patel",
         date="2026-06-15", project="Shield",
         text="Rotated the Auth Service signing key as recommended in DOC-104. Next rotation in 90 days. "
              "Status: done."),
    dict(id="TKT-203", type="ticket", title="Push notification delivery lag", author=None, assignee="Aarav Joshi",
         date="2026-09-18", project="Beacon",
         text="Notification Service delivery is delayed by up to 4 minutes because of consumer lag on the Kafka "
              "Event Bus. Status: open."),
    dict(id="TKT-204", type="ticket", title="Kafka consumer lag alert", author=None, assignee="Karan Singh",
         date="2026-09-02", project="Lumen",
         text="Alert fired for consumer lag on the Kafka Event Bus affecting the Analytics Pipeline. Fixed by "
              "adding partitions. Status: done."),
    dict(id="TKT-205", type="ticket", title="SSO login failures on Web App", author=None, assignee="Meera Iyer",
         date="2026-09-25", project="Shield",
         text="Some users cannot log in to the Web App through SSO because the Auth Service returns expired "
              "token errors. Status: open."),
    # ---------------------------------------------------------------- chats
    dict(id="CHAT-301", type="chat", title="#eng", author="Priya Nair", date="2026-02-20", project="Atlas",
         text="Going with Stripe for now, see DOC-101. We will revisit if settlement costs hurt."),
    dict(id="CHAT-302", type="chat", title="#payments", author="Sana Khan", date="2026-08-10", project="Atlas",
         text="Stripe settlement delays in INR are hurting cash flow. I am proposing Razorpay and writing the plan."),
    dict(id="CHAT-303", type="chat", title="#eng", author="Priya Nair", date="2026-08-14", project="Atlas",
         text="Approved: we are moving payments to Razorpay for India, see DOC-103. Stripe stays only for "
              "international customers until Q1."),
    dict(id="CHAT-304", type="chat", title="#infra", author="Karan Singh", date="2026-09-03", project=None,
         text="Kafka lag is fixed by adding partitions. Anyone changing Event Bus consumers, ping me first."),
    dict(id="CHAT-305", type="chat", title="#product", author="Neha Verma", date="2026-09-12", project="Beacon",
         text="Beacon launch slips to November because Notification Service lag is not fixed yet."),
    dict(id="CHAT-306", type="chat", title="#eng", author="Priya Nair", date="2026-09-30", project="Beacon",
         text="Rohan moves to Atlas full time. Aarav Joshi takes over ownership of the Notification Service."),
    dict(id="CHAT-307", type="chat", title="#support", author="Imran Ali", date="2026-10-01", project=None,
         text="Customers report push notifications arriving late and SSO login errors on the Web App."),
]

# Decisions with provenance. `supersedes` points at an older decision id.
DECISIONS = [
    dict(id="DEC-1", title="Use Stripe for payments", date="2026-02-20", decided_by="Priya Nair",
         rationale="Existing integration gives the fastest launch.", sources=["CHAT-301", "DOC-101"]),
    dict(id="DEC-2", title="Migrate payments to Razorpay (Stripe only for international until Q1)",
         date="2026-08-14", decided_by="Priya Nair",
         rationale="INR settlement delays and FX fees with Stripe.", sources=["CHAT-303", "DOC-103"],
         supersedes="DEC-1"),
    dict(id="DEC-3", title="Adopt Okta for company-wide SSO", date="2026-06-02", decided_by="Priya Nair",
         rationale="Threat model recommended SSO and key rotation.", sources=["DOC-105", "DOC-104"]),
    dict(id="DEC-4", title="Deliver payment webhooks idempotently via Kafka", date="2026-03-05",
         decided_by="Sana Khan", rationale="Avoid double-charging on duplicate webhook events.",
         sources=["DOC-102"]),
    dict(id="DEC-5", title="Transfer Notification Service ownership to Aarav Joshi", date="2026-09-30",
         decided_by="Priya Nair", rationale="Rohan moves to Atlas full time.", sources=["CHAT-306"]),
    dict(id="DEC-6", title="Delay Beacon launch to November", date="2026-09-12", decided_by="Neha Verma",
         rationale="Notification Service lag is not fixed yet.", sources=["CHAT-305"]),
]

SAMPLE_UPDATE = ("Update from Priya: we are postponing Okta because of cost. We will use Google Workspace SSO "
                 "instead. Dev Patel will revise the Shield rollout plan for Auth Service this month.")
