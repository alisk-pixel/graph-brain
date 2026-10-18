"""Detective team: three agents that investigate Nimbus Labs through ONE shared graph.
They never talk to each other. Every job, thought, finding and handoff lives in FalkorDB."""
import json
import sys
import uuid

import config
import cyber_data as cd
import cyber_graph as cg
import llm
from config import q, now

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TEAM = [
    ("Coordinator", "Runs the case and hands out jobs"),
    ("Forensics Analyst", "Studies what agents actually did"),
    ("System Architect", "Studies how access is wired and how to fix it"),
]

PATTERNS = {
    "ungranted_access": "Agent touched a resource it was never granted",
    "off_hours_activity": "Agent acted on sensitive data in the middle of the night",
    "inherited_privilege": "Agent reaches a resource through a chain of other agents",
    "unowned_agent": "Agent has no human owner",
}


# ----------------------------------------------------------------------------- small helpers
def _id():
    return uuid.uuid4().hex[:6]


def risk(sens, records, hour):
    score = int((sens or 1) * 10)
    if hour is not None and (hour < 5 or hour >= 22):
        score += 20
    score += min(30, int(records or 0) // 500)
    return min(100, score)


def label(score):
    return "CRITICAL" if score >= 85 else "HIGH" if score >= 65 else "MEDIUM" if score >= 40 else "LOW"


def llm_lines(instruction, items):
    """Ask the AI for one sentence per item. If the AI is unavailable, return nothing (we have fallbacks)."""
    try:
        out = llm.ask_json(f'{instruction}\nReturn ONLY JSON {{"notes": {{"<id>": "<one plain sentence>"}}}}\n'
                           f'Items: {json.dumps(items)}')
        notes = out.get("notes") or {}
        return {k: str(v) for k, v in notes.items() if k in items}
    except Exception:
        return {}


# ----------------------------------------------------------------------------- writing to the graph
def setup_team(g):
    for name, role in TEAM:
        q(g, "MERGE (d:Detective {name:$n}) SET d.role=$r", n=name, r=role)
    for key, desc in PATTERNS.items():
        q(g, "MERGE (p:Pattern {key:$k}) SET p.description=$d", k=key, d=desc)


def open_case(g, title):
    cid = "CASE-" + _id()
    q(g, "CREATE (c:Case {id:$id, title:$title, status:'open', opened:$ts})", id=cid, title=title, ts=now())
    return cid


def think(g, cid, who, text):
    """A detective's reasoning, saved in the graph AND shown on screen."""
    q(g, "MATCH (d:Detective {name:$w}), (c:Case {id:$cid}) "
         "CREATE (t:Thought {id:$id, text:$text, ts:$ts}) CREATE (d)-[:THOUGHT]->(t) CREATE (t)-[:IN_CASE]->(c)",
      w=who, cid=cid, id=_id(), text=text, ts=now())
    print(f"   [{who}] {text}")


def new_task(g, cid, kind, who, title, after=(), status="pending"):
    tid = "T-" + _id()
    q(g, "MATCH (c:Case {id:$cid}), (d:Detective {name:$w}) "
         "CREATE (k:Task {id:$id, kind:$kind, title:$title, status:$st, created:$ts}) "
         "CREATE (c)-[:HAS_TASK]->(k) CREATE (k)-[:ASSIGNED_TO]->(d)",
      cid=cid, w=who, id=tid, kind=kind, title=title, st=status, ts=now())
    for prev in after:
        q(g, "MATCH (x:Task {id:$a}), (y:Task {id:$b}) CREATE (x)-[:HANDOFF {ts:$ts}]->(y)", a=prev, b=tid, ts=now())
    return tid


def set_task(g, tid, status, summary=None):
    q(g, "MATCH (k:Task {id:$id}) SET k.status=$s, k.summary=$m, k.finished=$ts",
      id=tid, s=status, m=summary or "", ts=now())


def next_task(g, cid):
    """The next job whose earlier jobs are all done. Read from the graph, not from memory in Python."""
    rows = q(g, "MATCH (:Case {id:$cid})-[:HAS_TASK]->(k:Task {status:'pending'})-[:ASSIGNED_TO]->(d:Detective) "
                "OPTIONAL MATCH (p:Task)-[:HANDOFF]->(k) WHERE p.status <> 'done' "
                "WITH k, d, count(p) AS blockers WHERE blockers = 0 "
                "RETURN k.id, k.kind, k.title, d.name ORDER BY k.created LIMIT 1", cid=cid)
    return rows[0] if rows else None


def prior_flags(g, cid, agent):
    """Memory: how many times was this agent flagged in OTHER (earlier) cases?"""
    return q(g, "MATCH (c:Case)-[:HAS_FINDING]->(f:Finding)-[:ABOUT]->(a:AIAgent {name:$a}) "
                "WHERE c.id <> $cid RETURN count(f)", a=agent, cid=cid)[0][0]


def add_finding(g, cid, tid, who, kind, score, title, detail, agent=None, resource=None, patterns=()):
    score = int(min(100, score))
    fid = "F-" + _id()
    q(g, "MATCH (c:Case {id:$cid}), (k:Task {id:$tid}) "
         "CREATE (f:Finding {id:$id, kind:$kind, score:$score, severity:$sev, title:$title, detail:$detail, "
         "agent:$agent, resource:$res, by:$by, ts:$ts}) "
         "CREATE (c)-[:HAS_FINDING]->(f) CREATE (k)-[:PRODUCED]->(f)",
      cid=cid, tid=tid, id=fid, kind=kind, score=score, sev=label(score), title=title, detail=detail,
      agent=agent or "", res=resource or "", by=who, ts=now())
    if agent:
        q(g, "MATCH (f:Finding {id:$id}), (a:AIAgent {name:$a}) CREATE (f)-[:ABOUT]->(a)", id=fid, a=agent)
    if resource:
        q(g, "MATCH (f:Finding {id:$id}), (r:Resource {name:$r}) CREATE (f)-[:INVOLVES]->(r)", id=fid, r=resource)
    for p in patterns:
        q(g, "MATCH (f:Finding {id:$id}), (p:Pattern {key:$k}) CREATE (f)-[:MATCHES]->(p) "
             "SET p.seen = coalesce(p.seen, 0) + 1", id=fid, k=p)
    return fid


# ----------------------------------------------------------------------------- the detectives
def run_forensics(g, cid, tid):
    who = "Forensics Analyst"
    think(g, cid, who, "Opening the access log. Looking for agents that touched things they were never granted.")
    rows = cg.find_ungranted_access(g)
    think(g, cid, who, f"Found {len(rows)} suspicious access patterns. Scoring each one.")
    items = {}
    for r in rows:
        hour = int(r["earliest_hour"] or 0)
        score = risk(r["sensitivity"], r["records"], hour)
        prior = prior_flags(g, cid, r["agent"])
        if prior:
            score = min(100, score + 10)
            think(g, cid, who, f"Memory: {r['agent']} was already flagged {prior} time(s) in earlier cases. "
                               "Raising the score.")
        night = hour < 5 or hour >= 22
        patterns = ["ungranted_access"] + (["off_hours_activity"] if night else [])
        detail = (f"{int(r['records'])} records touched, {r['times']} time(s), first at {hour:02d}:00, "
                  f"sensitivity {int(r['sensitivity'])}/5")
        fid = add_finding(g, cid, tid, who, "ungranted_access", score,
                          f"{r['agent']} accessed {r['resource']} without permission", detail,
                          agent=r["agent"], resource=r["resource"], patterns=patterns)
        items[fid] = f"{r['agent']} accessed {r['resource']}: {detail}"
        think(g, cid, who, f"{label(score)}: {r['agent']} -> {r['resource']} ({detail}).")
    notes = llm_lines("You are a security forensics analyst. For each item write ONE plain-English sentence "
                      "on why it is worrying.", items)
    for fid, note in notes.items():
        q(g, "MATCH (f:Finding {id:$id}) SET f.analysis=$a", id=fid, a=note)
    if notes:
        think(g, cid, who, "Analyst notes written for each finding.")
    return f"{len(rows)} suspicious accesses logged"


def run_audit(g, cid, tid):
    who = "System Architect"
    think(g, cid, who, "Mapping who can reach what through chains of trust between agents.")
    chains = {}
    for c in cg.find_trust_chains(g):
        chains[(c["agent"], c["inherited_resource"])] = c
    orphans = cg.find_orphan_agents(g)
    think(g, cid, who, f"Found {len(chains)} hidden privilege chain(s) and {len(orphans)} agent(s) with no owner.")

    for (agent, resource), c in chains.items():
        hops = max(1, len(c["chain"]) - 2)
        score = int((c["sensitivity"] or 1) * 10) + 10 * hops
        used = q(g, "MATCH (a:AIAgent {name:$a})-[x:ACCESSED]->(r:Resource {name:$r}) RETURN count(x)",
                 a=agent, r=resource)[0][0]
        if used:
            score += 15
        prior = prior_flags(g, cid, agent)
        if prior:
            score = min(100, score + 10)
            think(g, cid, who, f"Memory: {agent} was flagged {prior} time(s) before. Raising the score.")
        score = min(100, score)
        path = " -> ".join(c["chain"])
        detail = f"Path: {path}. Never granted directly." + (" The agent has actually used this access." if used else "")
        fid = add_finding(g, cid, tid, who, "inherited_privilege", score,
                          f"{agent} reaches {resource} through {hops} hidden hand-off(s)", detail,
                          agent=agent, resource=resource, patterns=["inherited_privilege"])
        match = q(g, "MATCH (:Case {id:$cid})-[:HAS_FINDING]->(f:Finding {kind:'ungranted_access', agent:$a, "
                     "resource:$r}) RETURN f.id", cid=cid, a=agent, r=resource)
        if match:
            q(g, "MATCH (x:Finding {id:$x}), (y:Finding {id:$y}) CREATE (x)-[:EXPLAINS]->(y)", x=fid, y=match[0][0])
            think(g, cid, who, f"The Forensics Analyst already flagged {agent}'s access ({match[0][0]}). "
                               f"My chain ({path}) explains HOW it got in.")
        else:
            think(g, cid, who, f"{label(score)}: {path}.")

    for o in orphans:
        stats = q(g, "MATCH (a:AIAgent {name:$a}) OPTIONAL MATCH (a)-[x:ACCESSED]->(r:Resource) "
                     "RETURN count(x), max(r.sensitivity)", a=o["agent"])[0]
        touched, top = int(stats[0]), int(stats[1] or 0)
        score = min(100, 30 + 10 * top)
        prior = prior_flags(g, cid, o["agent"])
        if prior:
            score = min(100, score + 10)
            think(g, cid, who, f"Memory: {o['agent']} was flagged {prior} time(s) before. Raising the score.")
        add_finding(g, cid, tid, who, "unowned_agent", score,
                    f"{o['agent']} has no human owner ({o['status']})",
                    f"Nobody is accountable for it. It made {touched} access(es), highest sensitivity {top}/5.",
                    agent=o["agent"], patterns=["unowned_agent"])
        think(g, cid, who, f"{label(score)}: {o['agent']} is an ownerless agent that touched {touched} resource(s).")
    return f"{len(chains)} chains, {len(orphans)} orphans"


def template_action(kind, agent, resource):
    if kind == "ungranted_access":
        return f"Revoke {agent}'s access to {resource} and review what it read."
    if kind == "inherited_privilege":
        return f"Cut the trust link that lets {agent} borrow access to {resource}."
    return f"Switch off {agent} until a named person owns it."


def run_remediation(g, cid, tid):
    who = "System Architect"
    rows = q(g, "MATCH (:Case {id:$cid})-[:HAS_FINDING]->(f:Finding) "
                "RETURN f.id, f.kind, f.agent, f.resource, f.score ORDER BY f.score DESC", cid=cid)
    think(g, cid, who, f"Reading {len(rows)} findings from the case file. Writing a fix for each, worst first.")
    base = {r[0]: template_action(r[1], r[2], r[3]) for r in rows}
    notes = llm_lines("Rewrite each fix as ONE clear plain-English action a manager can approve. "
                      "Keep the names exactly.", base)
    for rank, r in enumerate(rows, start=1):
        action = notes.get(r[0]) or base[r[0]]
        q(g, "MATCH (f:Finding {id:$f}) CREATE (x:Recommendation {id:$id, action:$a, priority:$p, "
             "status:'proposed', ts:$ts}) CREATE (f)-[:FIXED_BY]->(x)", f=r[0], id="R-" + _id(), a=action, p=rank, ts=now())
    think(g, cid, who, f"{len(rows)} recommendations saved, ranked by risk.")
    return f"{len(rows)} fixes proposed"


def run_close(g, cid, tid):
    who = "Coordinator"
    counts = {r[0]: r[1] for r in q(g, "MATCH (:Case {id:$cid})-[:HAS_FINDING]->(f:Finding) "
                                       "RETURN f.severity, count(f)", cid=cid)}
    top = q(g, "MATCH (:Case {id:$cid})-[:HAS_FINDING]->(f:Finding) RETURN f.title, f.score "
               "ORDER BY f.score DESC LIMIT 3", cid=cid)
    total = sum(counts.values())
    think(g, cid, who, f"Reviewing the case file: {total} findings ({counts}).")
    facts = f"{total} findings: {counts}. Top threats: " + "; ".join(t[0] for t in top)
    fallback = f"{total} findings. " + (f"Most urgent: {top[0][0]}." if top else "")
    verdict = llm_lines("Write a 2-sentence executive summary a CEO can read in 10 seconds. "
                        "Use the key 'verdict'.", {"verdict": facts}).get("verdict") or fallback
    q(g, "MATCH (c:Case {id:$cid}) SET c.status='closed', c.closed=$ts, c.verdict=$v, c.finding_count=$n",
      cid=cid, ts=now(), v=verdict, n=total)
    think(g, cid, who, "Case closed. Memory updated for next time.")
    return "case closed"


HANDLERS = {"sweep": run_forensics, "audit": run_audit, "remediate": run_remediation, "close": run_close}


# ----------------------------------------------------------------------------- the investigation
def investigate(g, title="Rogue agent sweep"):
    cg.load_security_layer(g)
    setup_team(g)
    cid = open_case(g, title)
    print(f"\nCase opened: {cid}\n")

    past = q(g, "MATCH (c:Case {status:'closed'}) RETURN count(c)")[0][0]
    top = q(g, "MATCH (p:Pattern) WHERE p.seen IS NOT NULL RETURN p.description, p.seen ORDER BY p.seen DESC LIMIT 1")
    if past and top:
        think(g, cid, "Coordinator", f"Memory: {past} earlier case(s) on file. Most common pattern so far: "
                                     f"'{top[0][0]}' (seen {top[0][1]} times).")
    else:
        think(g, cid, "Coordinator", "Memory: no earlier cases on file. This is a fresh investigation.")

    t0 = new_task(g, cid, "open", "Coordinator", "Open the case and plan", status="done")
    t1 = new_task(g, cid, "sweep", "Forensics Analyst", "Sweep the access log", after=[t0])
    t2 = new_task(g, cid, "audit", "System Architect", "Audit trust chains and ownership", after=[t0])
    t3 = new_task(g, cid, "remediate", "System Architect", "Write fixes", after=[t1, t2])
    new_task(g, cid, "close", "Coordinator", "Close the case", after=[t3])
    think(g, cid, "Coordinator", "Four jobs written to the graph. Handing out work through the graph.")

    for _ in range(12):
        job = next_task(g, cid)
        if not job:
            break
        tid, kind, title_, who = job
        print(f"\n>> {who} picks up: {title_}")
        q(g, "MATCH (k:Task {id:$id}) SET k.status='working'", id=tid)
        summary = HANDLERS[kind](g, cid, tid)
        set_task(g, tid, "done", summary)
    return cid


def print_case_file(g, cid):
    """Everything below is read BACK OUT of the database."""
    print("\n" + "=" * 60)
    print("CASE FILE (read back from the graph)")
    print("=" * 60)
    c = q(g, "MATCH (c:Case {id:$cid}) RETURN c.title, c.status, c.verdict", cid=cid)[0]
    print(f"{cid}: {c[0]}  [{c[1]}]\nVerdict: {c[2]}\n")
    print("Jobs and handoffs:")
    for r in q(g, "MATCH (:Case {id:$cid})-[:HAS_TASK]->(k:Task)-[:ASSIGNED_TO]->(d:Detective) "
                  "OPTIONAL MATCH (p:Task)-[:HANDOFF]->(k) "
                  "RETURN d.name, k.title, k.status, collect(p.title), k.created "
                  "ORDER BY k.created", cid=cid):
        print(f"  - {r[0]}: {r[1]} [{r[2]}]" + (f"  (after: {', '.join(r[3])})" if r[3] else ""))
    n = q(g, "MATCH (:Thought)-[:IN_CASE]->(:Case {id:$cid}) RETURN count(*)", cid=cid)[0][0]
    print(f"\nThoughts saved in the graph: {n}\n")
    print("Findings, worst first:")
    rows = q(g, "MATCH (:Case {id:$cid})-[:HAS_FINDING]->(f:Finding) OPTIONAL MATCH (f)-[:FIXED_BY]->(r:Recommendation) "
                "RETURN f.severity, f.score, f.title, f.analysis, r.action, f.agent ORDER BY f.score DESC", cid=cid)
    for r in rows:
        print(f"  [{r[0]} {r[1]}] {r[2]}")
        if r[3]:
            print(f"      Why it matters: {r[3]}")
        print(f"      Fix: {r[4]}")
    caught = {r[5] for r in rows if r[0] in ("CRITICAL", "HIGH")}
    ok = cd.ANSWER_KEY["ungranted_agents"].issubset(caught)
    print("\nALL 3 ROGUE AGENTS CAUGHT" if ok else "\nSOMETHING IS OFF: paste this output to me")


if __name__ == "__main__":
    g = config.company_graph("nimbus")
    case = investigate(g)
    print_case_file(g, case)
