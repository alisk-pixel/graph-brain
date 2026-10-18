"""CYBER-OVERSIGHT control room. Every number on this screen is read live from FalkorDB."""
import contextlib
import datetime

import pandas as pd
import streamlit as st

import company_brain as cb
import config
import cyber_graph as cg
import detectives as dt
import llm
import viz
from config import q

st.set_page_config(page_title="Cyber-Oversight", page_icon="🛰️", layout="wide")

SEV_ICON = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
AVATAR = {"Coordinator": "🧭", "Forensics Analyst": "🔬", "System Architect": "🏗️"}
AGENT_COLOR = {"Coordinator": "#e0e7ff", "Forensics Analyst": "#fecaca", "System Architect": "#bbf7d0"}

# ----------------------------------------------------------------------------- the brain must be alive
try:
    config.db().list_graphs()
except Exception as e:
    st.error(f"The detectives have no brain: can't reach FalkorDB.\n\n{e}")
    st.stop()

g = config.company_graph("nimbus")


# ----------------------------------------------------------------------------- helpers
def esc(s):
    return str(s).replace('"', "'")


def plant_rogue(g):
    """Live demo: a brand-new agent appears and breaks the rules."""
    if q(g, "MATCH (a:AIAgent {name:'Sales Assistant'}) RETURN count(a)")[0][0]:
        return False
    q(g, "MERGE (a:AIAgent {name:'Sales Assistant'}) SET a.purpose='Drafts sales emails', "
         "a.status='active', a.created='2026-10-12'")
    q(g, "MATCH (a:AIAgent {name:'Sales Assistant'}), (s:System {name:'Web App'}) MERGE (a)-[:RUNS_ON]->(s)")
    q(g, "MATCH (a:AIAgent {name:'Sales Assistant'}), (p:Person {name:'Neha Verma'}) MERGE (a)-[:DEPLOYED_BY]->(p)")
    q(g, "MATCH (a:AIAgent {name:'Sales Assistant'}), (r:Resource {name:'Support Ticket Archive'}) "
         "MERGE (a)-[x:GRANTED]->(r) SET x.scope='read', x.since='2026-10-12'")
    q(g, "MATCH (a:AIAgent {name:'Sales Assistant'}), (r:Resource {name:'Payment Card Tokens'}) "
         "CREATE (a)-[:ACCESSED {ts:'2026-10-16T01:30:00', hour:1, action:'read', volume:2500}]->(r)")
    return True


def wipe_history(g):
    for label in ("Recommendation", "Finding", "Thought", "Task", "Case", "Pattern"):
        q(g, f"MATCH (n:{label}) DETACH DELETE n")


def threat_map_dot(g):
    risk = {r[0]: r[1] for r in q(g, "MATCH (f:Finding) WHERE f.agent <> '' RETURN f.agent, max(f.score)")}
    orphans = {o["agent"] for o in cg.find_orphan_agents(g)}
    agents = q(g, "MATCH (a:AIAgent) OPTIONAL MATCH (a)-[:DEPLOYED_BY]->(p:Person) RETURN a.name, p.name")
    resources = q(g, "MATCH (r:Resource) RETURN r.name, r.sensitivity")
    grants = q(g, "MATCH (a:AIAgent)-[x:GRANTED]->(r:Resource) RETURN a.name, r.name, x.scope")
    rogue = q(g, "MATCH (a:AIAgent)-[x:ACCESSED]->(r:Resource) OPTIONAL MATCH (a)-[gr:GRANTED]->(r) "
                 "WITH a, r, gr, count(x) AS n, sum(x.volume) AS v WHERE gr IS NULL RETURN a.name, r.name, n, v")
    trust = q(g, "MATCH (a:AIAgent)-[:DELEGATES_TO]->(b:AIAgent) RETURN a.name, b.name")

    out = ["digraph G {", "rankdir=LR;", 'bgcolor="transparent";',
           'node [style="filled", fontname="Helvetica", fontsize=11];',
           'edge [fontname="Helvetica", fontsize=9];']
    for name, owner in agents:
        score = risk.get(name, 0)
        fill = "#fecaca" if score >= 65 else "#fde68a" if (score >= 40 or name in orphans) else "#bfdbfe"
        note = "NO OWNER" if name in orphans else f"owner: {owner}"
        out.append(f'"{esc(name)}" [shape=box, fillcolor="{fill}", label="{esc(name)}\\n{esc(note)}"];')
    for name, sens in resources:
        fill = {5: "#fca5a5", 4: "#fdba74", 3: "#fde68a"}.get(sens, "#bbf7d0")
        out.append(f'"{esc(name)}" [shape=cylinder, fillcolor="{fill}", label="{esc(name)}\\nsensitivity {sens}/5"];')
    for a, r, scope in grants:
        out.append(f'"{esc(a)}" -> "{esc(r)}" [color="#16a34a", label="allowed ({esc(scope)})"];')
    for a, r, n, v in rogue:
        out.append(f'"{esc(a)}" -> "{esc(r)}" [color="#dc2626", penwidth=3, fontcolor="#dc2626", '
                   f'label="NOT ALLOWED: {n}x, {v} records"];')
    for a, b in trust:
        out.append(f'"{esc(a)}" -> "{esc(b)}" [color="#7c3aed", style=dashed, label="trusts"];')
    out.append("}")
    return "\n".join(out)


def render_findings(g, cid):
    rows = q(g, "MATCH (:Case {id:$cid})-[:HAS_FINDING]->(f:Finding) OPTIONAL MATCH (f)-[:FIXED_BY]->(r:Recommendation) "
                "RETURN f.severity, f.score, f.title, f.detail, f.analysis, r.action ORDER BY f.score DESC", cid=cid)
    for sev, score, title, detail, analysis, action in rows:
        with st.container(border=True):
            st.markdown(f"#### {SEV_ICON.get(sev, '⚪')} {sev} · {score}/100 — {title}")
            st.write(detail)
            if analysis:
                st.caption(f"🔬 Forensics: {analysis}")
            if action:
                st.success(f"✅ Fix: {action}")


def agent_history(g, agent):
    names = [r[0] for r in q(g, "MATCH (a:AIAgent) RETURN a.name")]
    low = (agent or "").lower()
    match = next((n for n in names if n.lower() == low), None) or next((n for n in names if low and low in n.lower()), None)
    if not match:
        return {"error": f"unknown agent '{agent}'", "agents": names}
    owner = [r[0] for r in q(g, "MATCH (:AIAgent {name:$a})-[:DEPLOYED_BY]->(p:Person) RETURN p.name", a=match)]
    grants = [{"resource": r[0], "scope": r[1]} for r in q(
        g, "MATCH (:AIAgent {name:$a})-[x:GRANTED]->(r:Resource) RETURN r.name, x.scope", a=match)]
    acc = [{"resource": r[0], "when": r[1], "action": r[2], "records": r[3]} for r in q(
        g, "MATCH (:AIAgent {name:$a})-[x:ACCESSED]->(r:Resource) RETURN r.name, x.ts, x.action, x.volume ORDER BY x.ts", a=match)]
    finds = [{"severity": r[0], "title": r[1], "score": r[2]} for r in q(
        g, "MATCH (f:Finding)-[:ABOUT]->(:AIAgent {name:$a}) RETURN f.severity, f.title, f.score", a=match)]
    return {"agent": match, "human_owner": owner or "NONE", "allowed_to_touch": grants,
            "actually_touched": acc, "past_findings": finds}


def all_findings(g):
    return [{"case": r[0], "severity": r[1], "score": r[2], "title": r[3]} for r in q(
        g, "MATCH (c:Case)-[:HAS_FINDING]->(f:Finding) RETURN c.id, f.severity, f.score, f.title "
           "ORDER BY f.score DESC LIMIT 15")]


ROLE = """You are the Detective Team of Nimbus Labs (Coordinator, Forensics Analyst, System Architect).
You investigate rogue AI agents using ONLY the tools, which read a security knowledge graph.
Ground every claim in tool results. Answer in plain English for a non-technical executive, under 120 words."""


def ask_detectives(g, question):
    tools = {
        "ungranted_access": (lambda: cg.find_ungranted_access(g),
                             "args: {}. Agents that touched resources they were never granted."),
        "trust_chains": (lambda: cg.find_trust_chains(g),
                         "args: {}. Hidden privilege paths through agent-to-agent trust."),
        "ownerless_agents": (lambda: cg.find_orphan_agents(g), "args: {}. AI agents with no human owner."),
        "case_findings": (lambda: all_findings(g),
                          "args: {}. Worst findings across all investigations, with scores."),
        "agent_history": (lambda agent: agent_history(g, agent),
                          'args: {"agent": str}. One agent: owner, what it may touch, what it did, past findings.'),
        "blast_radius": (lambda system: cb.impact_of_outage(g, system),
                         'args: {"system": str}. What breaks if a company system is compromised, and who to alert.'),
        "who_owns": (lambda entity: cb.owner_of(g, entity),
                     'args: {"entity": str}. Current owner and ownership history of a system or project.'),
    }
    final, trace = llm.agent_loop(ROLE, question + '\nFinish with {"answer": "plain-English answer"}', tools, max_steps=6)
    return (final.get("answer") or str(final)), trace


class Live:
    """Shows the detectives' printed thoughts on screen as they happen."""
    def __init__(self, box):
        self.box, self.buf = box, ""

    def write(self, s):
        self.buf += s
        self.box.code(self.buf[-5000:], language=None)
        return len(s)

    def flush(self):
        pass


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🛰️ Cyber-Oversight")
    st.caption("Rogue Agent Matrix · powered by FalkorDB")
    loaded = cg.is_loaded(g) and cb.is_loaded(g)
    build = st.button("🧱 Build crime scene", disabled=loaded, use_container_width=True)
    launch = st.button("🕵️ Launch investigation", type="primary", disabled=not loaded, use_container_width=True)
    plant = st.button("🚨 Plant a NEW rogue agent", disabled=not loaded, use_container_width=True)
    wipe = st.button("🧹 Wipe case history", disabled=not loaded, use_container_width=True)

if build:
    with st.spinner("Building Nimbus Labs and planting the incidents (about a minute)..."):
        cg.load_security_layer(g)
    st.rerun()
if wipe:
    wipe_history(g)
    for k in ("case", "log", "asked"):
        st.session_state.pop(k, None)
    st.rerun()
if plant:
    if plant_rogue(g):
        st.toast("New rogue agent planted: Sales Assistant. Now launch the investigation!", icon="🚨")
    else:
        st.toast("Sales Assistant is already planted.")

st.markdown("# 🛰️ PROJECT CYBER-OVERSIGHT")
st.caption("A detective team of AI agents hunting rogue AI agents. Every job, thought and finding lives in the graph. "
           "Stop the database and this page goes dark.")

if not loaded:
    st.info("The crime scene isn't built yet. Click **Build crime scene** in the sidebar.")
    st.stop()

# ----------------------------------------------------------------------------- run the investigation live
if launch:
    st.subheader("🕵️ Detectives at work, live from the graph")
    box = st.empty()
    live = Live(box)
    try:
        with contextlib.redirect_stdout(live):
            new_case = dt.investigate(g)
        st.session_state["case"] = new_case
        st.session_state["log"] = live.buf
        st.success("Case closed. Scroll down for the case file.")
    except Exception as e:
        st.error(f"The investigation hit a problem: {e}")
elif st.session_state.get("log"):
    with st.expander("🕵️ Last investigation log"):
        st.code(st.session_state["log"][-6000:], language=None)

# ----------------------------------------------------------------------------- headline numbers
cases = q(g, "MATCH (c:Case) RETURN c.id, c.status, c.opened ORDER BY c.opened DESC")
case_ids = [c[0] for c in cases]
n_agents = q(g, "MATCH (a:AIAgent) RETURN count(a)")[0][0]
n_cases = q(g, "MATCH (c:Case {status:'closed'}) RETURN count(c)")[0][0]
n_find = q(g, "MATCH (f:Finding) RETURN count(f)")[0][0]

sel = None
if case_ids:
    want = st.session_state.get("case")
    idx = case_ids.index(want) if want in case_ids else 0
    sel = st.selectbox("Case file", case_ids, index=idx)
n_crit = 0
if sel:
    n_crit = q(g, "MATCH (:Case {id:$cid})-[:HAS_FINDING]->(f:Finding) WHERE f.severity = 'CRITICAL' RETURN count(f)",
               cid=sel)[0][0]

m1, m2, m3, m4 = st.columns(4)
m1.metric("AI agents monitored", n_agents)
m2.metric("Cases closed", n_cases)
m3.metric("Findings on record", n_find)
m4.metric("Critical in this case", n_crit)

with st.sidebar.expander("🧬 What lives in the graph"):
    rows = q(g, "MATCH (n) RETURN labels(n) AS l, count(n) AS c ORDER BY c DESC")
    st.dataframe(pd.DataFrame([{"node type": (r[0][0] if isinstance(r[0], list) and r[0] else str(r[0])),
                                "count": r[1]} for r in rows]), hide_index=True, use_container_width=True)

tab_case, tab_map, tab_think, tab_mem, tab_ask = st.tabs(
    ["🚨 Case File", "🗺️ Threat Map", "🧠 Detective Reasoning", "📚 Case Memory", "💬 Ask the Detectives"])

# ----------------------------------------------------------------------------- tab 1: case file
with tab_case:
    if not sel:
        st.info("No investigations yet. Click **Launch investigation** in the sidebar.")
    else:
        info = q(g, "MATCH (c:Case {id:$cid}) RETURN c.title, c.status, c.verdict", cid=sel)[0]
        st.markdown(f"### {info[0]} · `{sel}` · {info[1]}")
        if info[2]:
            st.info(f"**Verdict:** {info[2]}")
        render_findings(g, sel)

# ----------------------------------------------------------------------------- tab 2: threat map
with tab_map:
    st.subheader("Who can touch what, and who broke the rules")
    st.caption("🟦 normal agent · 🟧 suspicious or ownerless · 🟥 high risk · green arrow = allowed · "
               "red arrow = NOT allowed · purple dashed = trusts another agent")
    st.graphviz_chart(threat_map_dot(g), use_container_width=True)

# ----------------------------------------------------------------------------- tab 3: reasoning
with tab_think:
    if not sel:
        st.info("Launch an investigation first.")
    else:
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Every thought, saved in the graph")
            for who, text, _ts in q(g, "MATCH (d:Detective)-[:THOUGHT]->(t:Thought)-[:IN_CASE]->(:Case {id:$cid}) "
                                  "RETURN d.name, t.text, t.ts ORDER BY t.ts", cid=sel):
                with st.chat_message("assistant", avatar=AVATAR.get(who, "🤖")):
                    st.markdown(f"**{who}**  \n{text}")
        with right:
            st.subheader("Jobs and handoffs")
            rows = q(g, "MATCH (:Case {id:$cid})-[:HAS_TASK]->(k:Task)-[:ASSIGNED_TO]->(d:Detective) "
                        "OPTIONAL MATCH (p:Task)-[:HANDOFF]->(k) RETURN k.id, d.name, k.title, k.status, p.id, k.created "
                        "ORDER BY k.created", cid=sel)
            label = {r[0]: f"{r[1]}\\n{r[2]}" for r in rows}
            edges = [(label[r[4]], label[r[0]], "handoff") for r in rows if r[4] in label]
            colors = {label[r[0]]: AGENT_COLOR.get(r[1], "#e5e7eb") for r in rows}
            if edges:
                st.graphviz_chart(viz.edges_dot(edges, colors=colors), use_container_width=True)
            st.dataframe(pd.DataFrame([{"detective": r[1], "job": r[2], "status": r[3]} for r in rows]),
                         hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------------- tab 4: memory
with tab_mem:
    st.subheader("What the detectives remember across cases")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Patterns they keep seeing**")
        pats = q(g, "MATCH (p:Pattern) RETURN p.description AS d, coalesce(p.seen, 0) AS n ORDER BY n DESC")
        st.dataframe(pd.DataFrame(pats, columns=["pattern", "times seen"]), hide_index=True, use_container_width=True)
    with c2:
        st.markdown("**Repeat offenders**")
        offs = q(g, "MATCH (c:Case)-[:HAS_FINDING]->(f:Finding)-[:ABOUT]->(a:AIAgent) "
                    "RETURN a.name AS agent, count(DISTINCT c) AS cases, max(f.score) AS worst ORDER BY worst DESC")
        st.dataframe(pd.DataFrame(offs, columns=["agent", "cases flagged in", "worst score"]),
                     hide_index=True, use_container_width=True)
    st.markdown("**Case history**")
    hist = q(g, "MATCH (c:Case) RETURN c.id AS id, c.status AS status, c.finding_count AS findings, "
                "c.verdict AS verdict, c.opened AS opened ORDER BY opened DESC")
    st.dataframe(pd.DataFrame([{"case": r[0], "status": r[1], "findings": r[2], "verdict": r[3],
                                "opened": datetime.datetime.fromtimestamp(r[4]).strftime("%b %d %H:%M") if r[4] else ""}
                               for r in hist]), hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------------- tab 5: ask
with tab_ask:
    st.subheader("Ask the detectives anything")
    examples = ["Which agent is the most dangerous right now, and why?",
                "If Auth Service is compromised, what breaks and who do we alert?",
                "Which agents have no human owner?",
                "What should we fix first?"]
    cols = st.columns(len(examples))
    picked = None
    for col, ex in zip(cols, examples):
        if col.button(ex, key=f"ex_{ex}", use_container_width=True):
            picked = ex
    with st.form("ask_form", clear_on_submit=True):
        typed = st.text_input("Your question")
        go = st.form_submit_button("Ask")
    question = picked or (typed.strip() if go else None)
    st.session_state.setdefault("asked", [])
    if question:
        with st.spinner("The detectives are walking the graph..."):
            try:
                answer, trace = ask_detectives(g, question)
            except Exception as e:
                answer, trace = f"Something went wrong: {e}", []
        st.session_state["asked"].insert(0, {"q": question, "a": answer, "trace": trace})
    for item in st.session_state["asked"]:
        st.markdown(f"**🙋 {item['q']}**")
        with st.chat_message("assistant", avatar="🕵️"):
            st.markdown(item["a"])
            if item["trace"]:
                with st.expander("🔍 How the detectives found this (graph tools used)"):
                    for t in item["trace"]:
                        st.markdown(f"**Step {t['step']} · `{t['tool']}`** — {t.get('thought', '')}")
