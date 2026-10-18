# 🛰️ Project Cyber-Oversight: Rogue Agent Matrix

**A team of three AI detectives that hunts rogue AI agents inside a company, and keeps its entire brain (tasks, reasoning, findings and memory) in a FalkorDB graph.**

| Track | What this project does for it |
|---|---|
| **Connected Data** | Multi-hop OpenCypher traversals expose access that nobody granted directly: chains of trust between agents that end at a secret. |
| **Agent Memory** | Three agents coordinate only through shared `Task`, `Thought` and `Finding` nodes and `HANDOFF` edges, and remember earlier cases in the graph. |
| **Company Brain** | One graph holds the people, teams, systems and ownership of a company (Nimbus Labs), with AI agents, resources, permissions and access history layered on top. |

---

## The idea in 30 seconds

Companies are deploying AI agents faster than anyone can track them. Each agent is *allowed* to touch certain data, but nobody checks what it *actually* touches. Worse, an agent can quietly borrow power from another agent it trusts, or run with no human owner at all.

A permissions spreadsheet cannot see that. A graph can, because the danger is not in any single row. It is in the **connections**.

Cyber-Oversight watches a simulated company, **Nimbus Labs**, with 8 AI agents, 8 sensitive resources, 10 people, 5 teams and 8 systems. Three rogue-agent incidents are hidden in the data:

1. **Support Copilot** reads 15,000 customer records from the PII vault at 3 AM, something it was never granted.
2. **Release Bot** reaches the authentication signing keys through a chain of trust: `Release Bot → Deploy Helper → Key Rotation Agent → Auth Signing Keys`.
3. **Shadow Summarizer** is an unregistered agent with no human owner, reading payment tokens and the internal roadmap at night.

Three detectives investigate: a **Coordinator**, a **Forensics Analyst** and a **System Architect**.

---

## Why FalkorDB is the engine, not just storage

The detectives never call each other. They never pass results through Python variables. Everything that matters is a node or a relationship in FalkorDB:

- **Jobs are nodes.** The Coordinator writes `Task` nodes, assigns each to a `Detective`, and links them with `HANDOFF` edges.
- **The next job is chosen by a graph query.** A detective starts a job only when a Cypher query finds that every job it depends on is marked `done` in the database.
- **Every thought is a node.** Each line of reasoning is saved as a `Thought` linked to its `Case`.
- **Findings are nodes** linked to the agent and resource involved, to the job that produced them, and to the fix that was recommended.
- **Memory is the graph.** Earlier cases, findings and `Pattern` counters stay in the graph. A new case recalls them, and an agent flagged before gets a higher risk score.

**Take FalkorDB away and the system stops.** The control room shows a "the detectives have no brain" error and refuses to start. There are no tasks to pick up, no reasoning trail to show, no findings, and no memory. No copy of any of it is kept in Python.

(One honest note: the starting Nimbus Labs data is written in Python source files and loaded into the graph once. After that, every read comes from FalkorDB.)

---

## Graph data model

### Nodes

| Label | What it is | Key properties |
|---|---|---|
| `Person` | An employee | `name`, `role` |
| `Team` | A team | `name` |
| `System` | A company system (Auth Service, Payments API, Kafka Event Bus...) | `name`, `description` |
| `Project` | A company project | `name`, `description`, `status` |
| `AIAgent` | An AI agent working inside the company | `name`, `purpose`, `status`, `created` |
| `Resource` | A sensitive asset (PII vault, signing keys...) | `name`, `kind`, `sensitivity` (1 to 5) |
| `Detective` | One of the three investigators | `name`, `role` |
| `Case` | One investigation | `id`, `title`, `status`, `opened`, `closed`, `verdict` |
| `Task` | A job on the shared case board | `id`, `kind`, `title`, `status`, `created`, `finished`, `summary` |
| `Thought` | One line of a detective's reasoning | `id`, `text`, `ts` |
| `Finding` | A piece of evidence or a vulnerability | `id`, `kind`, `score`, `severity`, `title`, `detail`, `analysis` |
| `Pattern` | A recurring threat pattern (the memory counter) | `key`, `description`, `seen` |
| `Recommendation` | A proposed fix | `id`, `action`, `priority`, `status` |

### Relationships

**The company fabric**

| Relationship | Meaning |
|---|---|
| `(Person)-[:MEMBER_OF]->(Team)` | Who belongs to which team |
| `(System)-[:DEPENDS_ON]->(System)` | Which system needs which |
| `(Person or Team)-[:OWNS]->(System)` | Ownership, with `since` and `until` dates |
| `(Person)-[:LEADS]->(Project)` and `(Project)-[:USES]->(System)` | Who runs what work, on which systems |

**The security layer**

| Relationship | Meaning |
|---|---|
| `(AIAgent)-[:DEPLOYED_BY]->(Person)` | The human who owns the agent. No such edge means an ownerless agent. |
| `(AIAgent)-[:RUNS_ON]->(System)` | Where the agent lives |
| `(Resource)-[:STORED_IN]->(System)` | Where the asset is kept |
| `(AIAgent)-[:GRANTED {scope, since}]->(Resource)` | What the agent is officially allowed to touch |
| `(AIAgent)-[:DELEGATES_TO]->(AIAgent)` | **Trust.** This agent hands work to, and relies on, that agent |
| `(AIAgent)-[:ACCESSED {ts, hour, action, volume}]->(Resource)` | What the agent actually touched, when, and how many records |

**The case board (the agents' shared brain)**

| Relationship | Meaning |
|---|---|
| `(Case)-[:HAS_TASK]->(Task)` | The jobs in a case |
| `(Task)-[:ASSIGNED_TO]->(Detective)` | Who must do the job |
| `(Task)-[:HANDOFF {ts}]->(Task)` | "This job must finish before that one starts" (the chain of custody) |
| `(Detective)-[:THOUGHT]->(Thought)-[:IN_CASE]->(Case)` | The saved reasoning trail |
| `(Case)-[:HAS_FINDING]->(Finding)` and `(Task)-[:PRODUCED]->(Finding)` | Evidence and who produced it |
| `(Finding)-[:ABOUT]->(AIAgent)` and `(Finding)-[:INVOLVES]->(Resource)` | What the evidence is about |
| `(Finding)-[:MATCHES]->(Pattern)` | Links evidence to recurring patterns, which feeds memory |
| `(Finding)-[:EXPLAINS]->(Finding)` | One detective's finding explaining another's |
| `(Finding)-[:FIXED_BY]->(Recommendation)` | The proposed fix |

---

## The threat-hunting queries

### Query 1: hidden privilege through chains of trust (multi-hop)

An agent that was **never granted** a resource, but reaches it by following `DELEGATES_TO` links to an agent that was. This is the exact query the app runs.

```cypher
MATCH p=(a:AIAgent)-[:DELEGATES_TO*1..5]->(b:AIAgent)-[:GRANTED]->(r:Resource)
OPTIONAL MATCH (a)-[d:GRANTED]->(r)
WITH p, a, r, d WHERE d IS NULL
RETURN a.name, r.name, r.sensitivity, [n IN nodes(p) | n.name]
```

It returns the hidden path for Release Bot:

```
Release Bot → Deploy Helper → Key Rotation Agent → Auth Signing Keys
```

Three hops across four nodes, and no row in any permissions list says Release Bot may touch those keys. It also catches Deploy Helper, which inherits the same access one hop earlier.

### Query 2: the shortest route to the signing keys

The same discovery, asked as a shortest-path question. The `shortestPath` function finds the quickest trust route from the suspect to the agent that holds the keys, and the second `MATCH` adds the final hop to the resource. Paste it into the FalkorDB browser to explore the chain.

```cypher
MATCH (a:AIAgent {name: 'Release Bot'}), (b:AIAgent {name: 'Key Rotation Agent'})
WITH shortestPath((a)-[:DELEGATES_TO*..5]->(b)) AS p
MATCH (k:AIAgent {name: 'Key Rotation Agent'})-[:GRANTED]->(r:Resource {name: 'Auth Signing Keys'})
RETURN [n IN nodes(p) | n.name] + [r.name] AS chain, length(p) + 1 AS hops
```

Expected result: the same four-node chain, with `hops = 3`.

> Note: the control room runs Query 1 and the other queries in `cyber_graph.py`. Query 2 is provided as a standalone way to explore the chain and depends on your FalkorDB version supporting `shortestPath`.

---

## How a case runs

1. **Coordinator** opens a `Case`, recalls earlier cases from the graph ("Memory: 1 earlier case on file"), and writes the jobs to the graph.
2. **Forensics Analyst** reads its job from the graph, finds agents that touched resources they were never granted, and scores each one.
3. **System Architect** reads its job from the graph, finds hidden trust chains and ownerless agents, then writes a recommended fix for every finding.
4. **Coordinator** closes the case with a plain-English verdict, which is saved on the `Case` node.

**How the scoring works.** It is simple, visible rules, not a black box: more sensitive data means more points, night-time activity adds points, large volumes add points, longer trust chains add points, and an agent flagged in an earlier case gets extra points. The totals map to CRITICAL, HIGH, MEDIUM and LOW.

**What the AI does.** The graph finds and scores the threats. Gemini writes the plain-English explanations, the fix wording, the executive verdict, and answers questions in the "Ask the Detectives" tab. If Gemini is slow or unavailable, the detectives fall back to built-in wording and still finish the case.

---

## The control room

Run it and you get one screen with five tabs:

| Tab | What you see |
|---|---|
| 🚨 Case File | Every finding with severity, why it matters, and the fix |
| 🗺️ Threat Map | Green arrows are allowed access, red arrows are rule-breaking access, purple dashed arrows are trust between agents. Agents are coloured by risk. |
| 🧠 Detective Reasoning | Every thought and handoff, read straight from the database |
| 📚 Case Memory | Patterns seen, repeat offenders, case history |
| 💬 Ask the Detectives | Ask any question in plain English and watch which graph tools were used |

The sidebar has four buttons: **Build crime scene**, **Launch investigation**, **Plant a NEW rogue agent** (adds a fresh threat live so the detectives can catch it), and **Wipe case history**.

---

## Setup (Windows and Mac)

You need three things: **Python 3.10 or newer**, a **FalkorDB** database, and a free **Gemini API key** from Google AI Studio.

### Step 1: Get the code

Download this repository as a ZIP and unzip it, or run `git clone <your-repo-url>`. Remember where the folder is.

### Step 2: Get a FalkorDB database

- **Option A (easiest): FalkorDB Cloud.** Create a free instance on their website and keep the host, port, username and password it shows you.
- **Option B: run it on your own computer** with Docker:
  ```
  docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest
  ```
  With this option you do not need to set any `FALKOR_` variables, only the Gemini key.

### Step 3: Open a terminal in the project folder

- **Windows:** open the Start menu, type `cmd`, press Enter, then type `cd ` followed by the folder path, for example `cd C:\Users\You\Desktop\graph-brain`.
- **Mac:** open the Terminal app, then type `cd ` followed by the folder path, for example `cd ~/Desktop/graph-brain`.

### Step 4: Install the libraries

- **Windows:** `pip install -r requirements.txt`
- **Mac:** `pip3 install -r requirements.txt`

### Step 5: Tell the app your secrets

These live only in your terminal window. They are never written into any file. Replace the placeholders with your own values.

**Windows (Command Prompt, no quotation marks):**
```
set GEMINI_API_KEY=your-gemini-key
set FALKOR_HOST=your-falkordb-host
set FALKOR_PORT=your-port
set FALKOR_USER=your-username
set FALKOR_PASSWORD=your-password
set FALKOR_SSL=false
```

**Mac (Terminal):**
```
export GEMINI_API_KEY="your-gemini-key"
export FALKOR_HOST="your-falkordb-host"
export FALKOR_PORT="your-port"
export FALKOR_USER="your-username"
export FALKOR_PASSWORD="your-password"
export FALKOR_SSL="false"
```

> **If it hangs on connecting:** switch `FALKOR_SSL` between `true` and `false`. Some instances need secure mode and some do not. If you set the variables in one window, run everything in that same window.

### Step 6: Start the control room

- **Windows:** `python -m streamlit run control_room.py`
- **Mac:** `python3 -m streamlit run control_room.py`

A browser page opens. Click **Build crime scene** (about a minute), then **Launch investigation**. Run the investigation a second time to see the detectives recall the first case.

### Optional: quick self-tests (no browser)

```
python cyber_graph.py
python detectives.py
```

The first should end with `ALL 3 INCIDENTS CAN BE FOUND`. The second should end with `ALL 3 ROGUE AGENTS CAUGHT`. (Use `python3` on Mac.)

### Prove the graph is the brain

Stop FalkorDB, or set `FALKOR_PORT` to a wrong number, and refresh the page. The control room shows an error and refuses to start. No database, no detectives.

---

## Project files

| File | Purpose |
|---|---|
| `control_room.py` | The live control-room screen |
| `detectives.py` | The three detectives and their graph-based coordination and memory |
| `cyber_graph.py` | Builds the security layer and holds the investigation queries |
| `cyber_data.py` | The AI agents, resources, permissions, trust links and access history |
| `company_brain.py` and `company_data.py` | The Nimbus Labs company graph (people, teams, systems, ownership) |
| `viz.py` | Small Graphviz drawing helpers |
| `config.py` | The FalkorDB connection, read from environment variables |
| `llm.py` | The Gemini helper |

---

## Honest notes

- Nimbus Labs and all of its data are simulated. No real company data is used.
- This is a hackathon prototype built to show how a graph makes AI-agent oversight explainable. It is not a production security product.
- Never commit your Gemini key or database password. They belong in environment variables only.
