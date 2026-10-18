"""Security layer for Nimbus Labs: AI agents, what they may touch, and what they actually did."""

# (name, kind, sensitivity 1-5, lives_in_system)
RESOURCES = [
    ("Customer PII Vault", "database", 5, "Postgres Primary"),
    ("Payment Card Tokens", "secrets", 5, "Payments API"),
    ("Auth Signing Keys", "secrets", 5, "Auth Service"),
    ("Analytics Warehouse", "dataset", 3, "Analytics Pipeline"),
    ("Kafka Payment Events", "stream", 3, "Kafka Event Bus"),
    ("Internal Roadmap Docs", "documents", 3, "Web App"),
    ("Support Ticket Archive", "documents", 2, "Web App"),
    ("Notification Templates", "content", 1, "Notification Service"),
]

# (agent, purpose, status, deployed_by or None, runs_on_system, created)
AGENTS = [
    ("Billing Bot", "Reconciles payments and refunds", "active", "Sana Khan", "Payments API", "2026-03-10"),
    ("Support Copilot", "Drafts replies to customer tickets", "active", "Imran Ali", "Web App", "2026-05-02"),
    ("Analytics Agent", "Builds daily usage reports", "active", "Ishita Rao", "Analytics Pipeline", "2026-04-20"),
    ("Notif Agent", "Tunes notification wording", "active", "Aarav Joshi", "Notification Service", "2026-09-01"),
    ("Release Bot", "Ships new versions of services", "active", "Karan Singh", "Kafka Event Bus", "2026-02-11"),
    ("Deploy Helper", "Prepares deployment steps", "active", "Karan Singh", "Kafka Event Bus", "2026-02-15"),
    ("Key Rotation Agent", "Rotates signing keys every 90 days", "active", "Dev Patel", "Auth Service", "2026-06-15"),
    ("Shadow Summarizer", "Summarizes internal documents", "unregistered", None, "Notification Service", "2026-08-01"),
]

# (agent, resource, scope, since) = what each agent is OFFICIALLY allowed to touch
GRANTS = [
    ("Billing Bot", "Payment Card Tokens", "read", "2026-03-10"),
    ("Billing Bot", "Kafka Payment Events", "read", "2026-03-10"),
    ("Support Copilot", "Support Ticket Archive", "read", "2026-05-02"),
    ("Support Copilot", "Notification Templates", "read", "2026-05-02"),
    ("Analytics Agent", "Analytics Warehouse", "read-write", "2026-04-20"),
    ("Analytics Agent", "Kafka Payment Events", "read", "2026-04-20"),
    ("Notif Agent", "Notification Templates", "read-write", "2026-09-01"),
    ("Release Bot", "Kafka Payment Events", "read", "2026-02-11"),
    ("Key Rotation Agent", "Auth Signing Keys", "read-write", "2026-06-15"),
]

# (from_agent, to_agent) = "this agent hands work to / trusts that agent"
DELEGATIONS = [
    ("Release Bot", "Deploy Helper"),
    ("Deploy Helper", "Key Rotation Agent"),
]

# (agent, resource, timestamp, action, volume = how many records touched)
EVENTS = [
    # ---- normal everyday behaviour (the "noise" the detectives must see past)
    ("Billing Bot", "Payment Card Tokens", "2026-10-08T10:05:00", "read", 40),
    ("Billing Bot", "Payment Card Tokens", "2026-10-09T11:20:00", "read", 55),
    ("Billing Bot", "Kafka Payment Events", "2026-10-10T14:00:00", "read", 300),
    ("Support Copilot", "Support Ticket Archive", "2026-10-08T09:30:00", "read", 25),
    ("Support Copilot", "Support Ticket Archive", "2026-10-10T15:45:00", "read", 30),
    ("Support Copilot", "Notification Templates", "2026-10-09T13:10:00", "read", 5),
    ("Analytics Agent", "Analytics Warehouse", "2026-10-08T08:00:00", "write", 5000),
    ("Analytics Agent", "Analytics Warehouse", "2026-10-09T08:00:00", "write", 5200),
    ("Analytics Agent", "Kafka Payment Events", "2026-10-09T08:05:00", "read", 800),
    ("Notif Agent", "Notification Templates", "2026-10-09T16:00:00", "write", 12),
    ("Notif Agent", "Notification Templates", "2026-10-11T10:30:00", "read", 8),
    ("Release Bot", "Kafka Payment Events", "2026-10-07T17:00:00", "read", 20),
    ("Key Rotation Agent", "Auth Signing Keys", "2026-09-14T04:00:00", "write", 1),
    # ---- INCIDENT 1: Support Copilot grabs the whole customer vault at 3 AM
    ("Support Copilot", "Customer PII Vault", "2026-10-11T03:12:00", "read", 15000),
    # ---- INCIDENT 2: Release Bot reaches the signing keys through a chain of trust
    ("Release Bot", "Auth Signing Keys", "2026-10-09T02:40:00", "read", 1),
    # ---- INCIDENT 3: an agent nobody owns reads secrets and the roadmap
    ("Shadow Summarizer", "Internal Roadmap Docs", "2026-10-10T23:50:00", "read", 40),
    ("Shadow Summarizer", "Payment Card Tokens", "2026-10-11T00:15:00", "read", 900),
]

# Used ONLY by our test script to check the detectives would find everything.
# This is never written into the database.
ANSWER_KEY = {
    "ungranted_agents": {"Support Copilot", "Release Bot", "Shadow Summarizer"},
    "chain_agent": "Release Bot",
    "orphan_agents": {"Shadow Summarizer"},
}
