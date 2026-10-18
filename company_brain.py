"""Company Brain (Track 03).

People, teams, systems, projects, docs, tickets, chats and decisions live in ONE graph.
  - Every decision links to the source it came from (RECORDED_IN) -> answers with clear sources
  - Decisions supersede each other (SUPERSEDES, status, valid_to)      -> knowledge stays current
  - Ownership has history (OWNS{since,until})                          -> who owns what, now and before
  - Contributions (CONTRIBUTED) + MENTIONS                             -> who knows what
New text can be ingested at any time; an LLM spots decisions/ownership changes and updates the graph.
"""
import datetime
import difflib
import re

import llm
from company_data import (ALIASES, DECISIONS, DEPENDS_ON, OWNS, PEOPLE, PROJECTS, SOURCES, SYSTEMS, TEAMS)
from config import q

CITE = re.compile(r"\b(?:DOC|TKT|CHAT|NEW)-\d+\b")


# ----------------------------------------------------------------------------- loading
def is_loaded(g):
    try:
        return q(g, "MATCH (p:Person) RETURN count(p)")[0][0] > 0
    except Exception:
        return False


def reset(g):
    try:
        g.delete()
    except Exception:
        pass


def _entities(g):
    people = [r[0] for r in q(g, "MATCH (p:Person) RETURN p.name")]
    firsts = [n.split()[0].lower() for n in people]
    ents = []
    for n in people:
        al = [n.lower()]
        if firsts.count(n.split()[0].lower()) == 1:
            al.append(n.split()[0].lower())
        ents.append(("Person", n, al))
    for (n,) in q(g, "MATCH (s:System) RETURN s.name"):
        ents.append(("System", n, [n.lower()] + ALIASES.get(n, [])))
    for (n,) in q(g, "MATCH (p:Project) RETURN p.name"):
        ents.append(("Project", n, [n.lower()]))
    return ents


def link_mentions(g, source_id, text):
    for label, name, aliases in _entities(g):
        if any(re.search(r"\b" + re.escape(a) + r"\b", text, re.I) for a in aliases):
            q(g, f"MATCH (x:Source {{id:$id}}), (e:{label} {{name:$n}}) MERGE (x)-[:MENTIONS]->(e)", id=source_id, n=name)


def add_source(g, s):
    q(g, "MERGE (x:Source {id:$id}) SET x.type=$type, x.title=$title, x.date=$date, x.text=$text, x.project=$project",
      id=s["id"], type=s["type"], title=s["title"], date=s["date"], text=s["text"], project=s.get("project") or "")
    if s.get("author"):
        q(g, "MATCH (p:Person {name:$a}), (x:Source {id:$id}) MERGE (p)-[c:CONTRIBUTED]->(x) SET c.role='author'",
          a=s["author"], id=s["id"])
    if s.get("assignee"):
        q(g, "MATCH (p:Person {name:$a}), (x:Source {id:$id}) MERGE (p)-[c:CONTRIBUTED]->(x) SET c.role='assignee'",
          a=s["assignee"], id=s["id"])
    if s.get("project"):
        q(g, "MATCH (x:Source {id:$id}), (p:Project {name:$p}) MERGE (x)-[:ABOUT]->(p)", id=s["id"], p=s["project"])
    link_mentions(g, s["id"], s["title"] + " " + s["text"])


def supersede(g, new_id, old_id, date):
    q(g, "MATCH (n:Decision {id:$n}), (o:Decision {id:$o}) MERGE (n)-[:SUPERSEDES]->(o) "
         "SET o.status='superseded', o.valid_to=$d", n=new_id, o=old_id, d=date)


def add_decision(g, d):
    q(g, "MERGE (x:Decision {id:$id}) SET x.title=$title, x.date=$date, x.rationale=$r, x.status='current', "
         "x.valid_from=$date", id=d["id"], title=d["title"], date=d["date"], r=d.get("rationale") or "")
    if d.get("decided_by"):
        q(g, "MATCH (x:Decision {id:$id}), (p:Person {name:$p}) MERGE (x)-[:DECIDED_BY]->(p)", id=d["id"], p=d["decided_by"])
    for sid in d.get("sources", []):
        q(g, "MATCH (x:Decision {id:$id}), (s:Source {id:$s}) MERGE (x)-[:RECORDED_IN]->(s)", id=d["id"], s=sid)


def set_owner(g, system, new_owner, date):
    q(g, "MATCH (o)-[r:OWNS]->(s:System {name:$s}) WHERE r.until IS NULL SET r.until=$d", s=system, d=date)
    q(g, "MATCH (o {name:$o}), (s:System {name:$s}) MERGE (o)-[r:OWNS]->(s) SET r.since=$d, r.until=NULL",
      o=new_owner, s=system, d=date)


def load_sample(g):
    """Build the whole Nimbus Labs graph from the sample dataset."""
    for t in TEAMS:
        q(g, "MERGE (:Team {name:$n})", n=t)
    for name, role, team in PEOPLE:
        q(g, "MERGE (p:Person {name:$n}) SET p.role=$r MERGE (t:Team {name:$t}) MERGE (p)-[:MEMBER_OF]->(t)",
          n=name, r=role, t=team)
    for name, desc in SYSTEMS:
        q(g, "MERGE (s:System {name:$n}) SET s.description=$d", n=name, d=desc)
    for a, b in DEPENDS_ON:
        q(g, "MATCH (x:System {name:$a}), (y:System {name:$b}) MERGE (x)-[:DEPENDS_ON]->(y)", a=a, b=b)
    for owner, system, since, until in OWNS:
        if until:
            q(g, "MATCH (o {name:$o}), (s:System {name:$s}) MERGE (o)-[r:OWNS]->(s) SET r.since=$since, r.until=$until",
              o=owner, s=system, since=since, until=until)
        else:
            q(g, "MATCH (o {name:$o}), (s:System {name:$s}) MERGE (o)-[r:OWNS]->(s) SET r.since=$since",
              o=owner, s=system, since=since)
    for name, desc, status, leader, systems in PROJECTS:
        q(g, "MERGE (p:Project {name:$n}) SET p.description=$d, p.status=$s", n=name, d=desc, s=status)
        q(g, "MATCH (p:Project {name:$n}), (l:Person {name:$l}) MERGE (l)-[:LEADS]->(p)", n=name, l=leader)
        for s in systems:
            q(g, "MATCH (p:Project {name:$n}), (s:System {name:$s}) MERGE (p)-[:USES]->(s)", n=name, s=s)
    for s in SOURCES:
        add_source(g, s)
    for d in DECISIONS:
        add_decision(g, d)
    for d in DECISIONS:
        if d.get("supersedes"):
            supersede(g, d["id"], d["supersedes"], d["date"])
    try:
        g.query("CREATE INDEX FOR (p:Person) ON (p.name)")
        g.query("CREATE INDEX FOR (s:System) ON (s.name)")
    except Exception:
        pass


# ----------------------------------------------------------------------------- keeping knowledge current
def ingest_text(g, text, author=None, date=None, kind="note", project=None):
    """Add new knowledge. The LLM spots decisions + ownership changes and the graph is updated."""
    date = date or datetime.date.today().isoformat()
    n = q(g, "MATCH (s:Source) WHERE s.id STARTS WITH 'NEW-' RETURN count(s)")[0][0] + 1
    sid = f"NEW-{n:03d}"
    add_source(g, dict(id=sid, type=kind, title=f"New {kind}", author=author, date=date, text=text, project=project))
    mentions = [r[0] for r in q(g, "MATCH (:Source {id:$id})-[:MENTIONS]->(e) RETURN e.name", id=sid)]

    current = [{"id": r[0], "title": r[1]} for r in q(
        g, "MATCH (d:Decision) WHERE d.status = 'current' RETURN d.id, d.title")]
    systems = [r[0] for r in q(g, "MATCH (s:System) RETURN s.name")]
    out = llm.ask_json(f"""You maintain a company knowledge graph. Today is {date}. From the text, extract ONLY
what it clearly states. Return ONLY JSON:
{{"decisions": [{{"title": "...", "rationale": "...", "decided_by": "person name or null",
                 "supersedes_id": "id from current decisions or null"}}],
 "ownership_changes": [{{"system": "one of the systems", "new_owner": "person or team name"}}]}}
Current decisions: {current}
Systems: {systems}
Text: {text}""")

    summary = {"source_id": sid, "mentions": mentions, "new_decisions": [], "superseded": [], "ownership_changes": []}
    count = q(g, "MATCH (d:Decision) RETURN count(d)")[0][0]
    people = {r[0].lower(): r[0] for r in q(g, "MATCH (p:Person) RETURN p.name")}
    valid_old = {d["id"] for d in current}
    for d in out.get("decisions") or []:
        if not d.get("title"):
            continue
        count += 1
        did = f"DEC-{count}"
        by = people.get((d.get("decided_by") or "").lower()) or author
        add_decision(g, dict(id=did, title=d["title"], date=date, decided_by=by,
                             rationale=d.get("rationale"), sources=[sid]))
        summary["new_decisions"].append({"id": did, "title": d["title"]})
        if d.get("supersedes_id") in valid_old:
            supersede(g, did, d["supersedes_id"], date)
            summary["superseded"].append(d["supersedes_id"])
    for c in out.get("ownership_changes") or []:
        ent = resolve_entity(g, c.get("system") or "", ("System",))
        new_owner = resolve_entity(g, c.get("new_owner") or "", ("Person", "Team"))
        if ent and new_owner:
            set_owner(g, ent[1], new_owner[1], date)
            summary["ownership_changes"].append(f"{ent[1]} -> {new_owner[1]}")
    return summary


def stale_report(g):
    """Docs that record decisions which were later superseded = possibly outdated knowledge."""
    rows = q(g, "MATCH (d:Decision) WHERE d.status = 'superseded' MATCH (d)-[:RECORDED_IN]->(s:Source) "
                "OPTIONAL MATCH (n:Decision)-[:SUPERSEDES]->(d) "
                "RETURN DISTINCT s.id, s.title, d.id, d.title, n.id, n.title")
    return [{"source": r[0], "source_title": r[1], "old_decision": f"{r[2]}: {r[3]}",
             "replaced_by": f"{r[4]}: {r[5]}" if r[4] else None} for r in rows]


# ----------------------------------------------------------------------------- graph tools
def resolve_entity(g, name, labels=("System", "Project", "Person", "Team")):
    low = (name or "").strip().lower()
    if not low:
        return None
    cands = {}
    for label in labels:
        for (n,) in q(g, f"MATCH (x:{label}) RETURN x.name"):
            cands[n.lower()] = (label, n)
    if "System" in labels:
        for sysname, al in ALIASES.items():
            for a in al:
                cands.setdefault(a, ("System", sysname))
    if low in cands:
        return cands[low]
    m = difflib.get_close_matches(low, list(cands), n=1, cutoff=0.6)
    if m:
        return cands[m[0]]
    for k, v in cands.items():
        if low in k or k in low:
            return v
    return None


def who_knows(g, topic):
    ent = resolve_entity(g, topic, ("System", "Project"))
    if not ent:
        return {"error": f"don't know '{topic}'", "try": search_sources(g, topic)}
    label, name = ent
    rows = q(g, "MATCH (p:Person)-[:CONTRIBUTED]->(s:Source)-[:MENTIONS]->(x {name:$n}) "
                "OPTIONAL MATCH (p)-[:MEMBER_OF]->(tm:Team) "
                "RETURN p.name, p.role, tm.name, count(DISTINCT s) AS n, collect(DISTINCT s.id) "
                "ORDER BY n DESC LIMIT 6", n=name)
    owners = {r[0] for r in q(g, "MATCH (o)-[r:OWNS]->(x {name:$n}) WHERE r.until IS NULL RETURN o.name", n=name)}
    leads = {r[0] for r in q(g, "MATCH (p:Person)-[:LEADS]->(x {name:$n}) RETURN p.name", n=name)}
    experts = []
    for person, role, team, n, ev in rows:
        score = n + (5 if person in owners else 0) + (3 if person in leads else 0)
        experts.append({"person": person, "role": role, "team": team, "sources_contributed": n,
                        "is_current_owner": person in owners, "leads_it": person in leads,
                        "score": score, "evidence": sorted(ev)})
    experts.sort(key=lambda e: -e["score"])
    return {"entity": name, "type": label, "current_owners": sorted(owners), "experts": experts}


def owner_of(g, entity):
    ent = resolve_entity(g, entity, ("System", "Project"))
    if not ent:
        return {"error": f"don't know '{entity}'"}
    label, name = ent
    if label == "Project":
        rows = q(g, "MATCH (p:Person)-[:LEADS]->(x:Project {name:$n}) RETURN p.name", n=name)
        return {"entity": name, "type": "Project", "led_by": [r[0] for r in rows]}
    rows = q(g, "MATCH (o)-[r:OWNS]->(s:System {name:$n}) RETURN o.name, r.since, r.until ORDER BY r.since", n=name)
    hist = [{"owner": r[0], "since": r[1], "until": r[2]} for r in rows]
    return {"entity": name, "type": "System", "current_owner": [h["owner"] for h in hist if not h["until"]],
            "history": hist}


def impact_of_outage(g, system):
    ent = resolve_entity(g, system, ("System",))
    if not ent:
        return {"error": f"unknown system '{system}'"}
    name = ent[1]
    rows = q(g, "MATCH p=(d:System)-[:DEPENDS_ON*1..5]->(s:System {name:$n}) "
                "RETURN d.name, min(length(p)) AS hops ORDER BY hops", n=name)
    affected = [{"system": r[0], "hops": r[1]} for r in rows]
    names = [name] + [a["system"] for a in affected]
    projects = [r[0] for r in q(g, "MATCH (p:Project)-[:USES]->(s:System) WHERE s.name IN $names RETURN DISTINCT p.name", names=names)]
    owners = [{"owner": r[0], "system": r[1]} for r in q(
        g, "MATCH (o)-[r:OWNS]->(s:System) WHERE s.name IN $names AND r.until IS NULL RETURN o.name, s.name", names=names)]
    edges = [[r[0], r[1]] for r in q(
        g, "MATCH (a:System)-[:DEPENDS_ON]->(b:System) WHERE a.name IN $names AND b.name IN $names RETURN a.name, b.name", names=names)]
    return {"system": name, "affected_systems": affected, "projects_at_risk": projects,
            "owners_to_alert": owners, "edges": edges}


def dependencies_of(g, system):
    ent = resolve_entity(g, system, ("System",))
    if not ent:
        return {"error": f"unknown system '{system}'"}
    rows = q(g, "MATCH p=(s:System {name:$n})-[:DEPENDS_ON*1..5]->(d:System) RETURN d.name, min(length(p)) AS hops ORDER BY hops", n=ent[1])
    return {"system": ent[1], "depends_on": [{"system": r[0], "hops": r[1]} for r in rows]}


def _decisions(g):
    rows = q(g, "MATCH (d:Decision) OPTIONAL MATCH (d)-[:DECIDED_BY]->(p:Person) "
                "RETURN d.id, d.title, d.date, d.status, d.rationale, p.name ORDER BY d.date")
    return [{"id": r[0], "title": r[1], "date": r[2], "status": r[3], "rationale": r[4], "decided_by": r[5]} for r in rows]


def _tokens(s):
    return [t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2]


def decision_trace(g, query):
    """Find decisions matching the query and trace each back to its sources and supersede chain."""
    toks = set(_tokens(query))
    scored = []
    for d in _decisions(g):
        hay = set(_tokens(d["id"] + " " + d["title"] + " " + (d["rationale"] or "")))
        s = len(toks & hay) + (5 if query.strip().lower() == d["id"].lower() else 0)
        if s:
            scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    matches = []
    for _, d in scored[:3]:
        srcs = q(g, "MATCH (:Decision {id:$id})-[:RECORDED_IN]->(s:Source) RETURN s.id, s.title, s.date", id=d["id"])
        older = q(g, "MATCH p=(:Decision {id:$id})-[:SUPERSEDES*1..5]->(o:Decision) "
                     "RETURN o.id, o.title, o.date, min(length(p)) AS h ORDER BY h", id=d["id"])
        newer = q(g, "MATCH (n:Decision)-[:SUPERSEDES*1..5]->(:Decision {id:$id}) RETURN DISTINCT n.id, n.title, n.date", id=d["id"])
        matches.append({**d, "sources": [{"id": r[0], "title": r[1], "date": r[2]} for r in srcs],
                        "supersedes": [{"id": r[0], "title": r[1], "date": r[2]} for r in older],
                        "superseded_by": [{"id": r[0], "title": r[1], "date": r[2]} for r in newer]})
    return {"matches": matches} if matches else {"matches": [], "note": "no decision matched"}


def list_decisions(g, status=None):
    ds = _decisions(g)
    return [d for d in ds if not status or d["status"] == status]


def search_sources(g, keyword, limit=5):
    toks = set(_tokens(keyword))
    rows = q(g, "MATCH (s:Source) RETURN s.id, s.type, s.title, s.date, s.text")
    scored = []
    for sid, typ, title, date, text in rows:
        hay = _tokens(title + " " + text)
        s = sum(1 for t in hay if t in toks)
        if s:
            scored.append((s, {"id": sid, "type": typ, "title": title, "date": date, "snippet": text[:200]}))
    scored.sort(key=lambda x: -x[0])
    return [x[1] for x in scored[: int(limit)]]


def read_source(g, source_id):
    rows = q(g, "MATCH (s:Source {id:$id}) OPTIONAL MATCH (p:Person)-[c:CONTRIBUTED]->(s) "
                "RETURN s.id, s.type, s.title, s.date, s.text, collect(p.name + ' (' + c.role + ')')", id=source_id)
    if not rows or rows[0][0] is None:
        return {"error": f"no source {source_id}"}
    r = rows[0]
    return {"id": r[0], "type": r[1], "title": r[2], "date": r[3], "text": r[4], "contributors": r[5]}


def project_timeline(g, project):
    ent = resolve_entity(g, project, ("Project",))
    if not ent:
        return {"error": f"unknown project '{project}'"}
    name = ent[1]
    src = q(g, "MATCH (s:Source)-[:ABOUT]->(:Project {name:$n}) RETURN s.id, s.type, s.title, s.date ORDER BY s.date", n=name)
    dec = q(g, "MATCH (d:Decision)-[:RECORDED_IN]->(:Source)-[:ABOUT]->(:Project {name:$n}) "
               "RETURN DISTINCT d.id, d.title, d.date, d.status ORDER BY d.date", n=name)
    return {"project": name,
            "sources": [{"id": r[0], "type": r[1], "title": r[2], "date": r[3]} for r in src],
            "decisions": [{"id": r[0], "title": r[1], "date": r[2], "status": r[3]} for r in dec]}


def person_profile(g, name):
    ent = resolve_entity(g, name, ("Person",))
    if not ent:
        return {"error": f"unknown person '{name}'"}
    n = ent[1]
    base = q(g, "MATCH (p:Person {name:$n}) OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team) RETURN p.role, t.name", n=n)[0]
    owns = [r[0] for r in q(g, "MATCH (p:Person {name:$n})-[r:OWNS]->(s:System) WHERE r.until IS NULL RETURN s.name", n=n)]
    leads = [r[0] for r in q(g, "MATCH (p:Person {name:$n})-[:LEADS]->(x:Project) RETURN x.name", n=n)]
    contrib = [{"id": r[0], "title": r[1], "date": r[2]} for r in q(
        g, "MATCH (p:Person {name:$n})-[:CONTRIBUTED]->(s:Source) RETURN s.id, s.title, s.date ORDER BY s.date DESC LIMIT 6", n=n)]
    return {"person": n, "role": base[0], "team": base[1], "owns": owns, "leads": leads, "recent_contributions": contrib}


def company_toolbox(g):
    return {
        "who_knows": (lambda topic: who_knows(g, topic),
                      'args: {"topic": system or project name}. Ranked experts (by contributions, ownership) with evidence ids.'),
        "owner_of": (lambda entity: owner_of(g, entity),
                     'args: {"entity": system or project}. Current owner and ownership history.'),
        "impact_of_outage": (lambda system: impact_of_outage(g, system),
                             'args: {"system": str}. What breaks if it goes down: dependents, projects, owners to alert.'),
        "dependencies_of": (lambda system: dependencies_of(g, system), 'args: {"system": str}. What it depends on.'),
        "decision_trace": (lambda query: decision_trace(g, query),
                           'args: {"query": keywords or decision id}. Decision, who decided, why, sources, and what it superseded / was superseded by.'),
        "list_decisions": (lambda status=None: list_decisions(g, status),
                           'args: {"status": "current|superseded|null"}. All decisions.'),
        "search_sources": (lambda keyword, limit=5: search_sources(g, keyword, limit),
                           'args: {"keyword": str, "limit": int}. Search docs, tickets and chats.'),
        "read_source": (lambda source_id: read_source(g, source_id), 'args: {"source_id": "DOC-101"}. Full text of one source.'),
        "project_timeline": (lambda project: project_timeline(g, project), 'args: {"project": str}. Sources and decisions over time.'),
        "person_profile": (lambda name: person_profile(g, name), 'args: {"name": str}. Role, team, what they own/lead/contributed.'),
    }


ROLE = """You are the Company Brain: an assistant that knows how a company works, using ONLY a knowledge graph of
people, teams, systems, projects, documents, tickets, chats and decisions. Ground every claim in tool results.
Cite sources inline using their ids like [DOC-103] or [CHAT-303]. Prefer CURRENT decisions and owners, and say
explicitly when something was superseded. If the graph doesn't contain the answer, say so."""


def ask(g, question):
    final, trace = llm.agent_loop(
        ROLE, question + '\nFinish with {"answer": "concise answer with inline [IDs]", "sources": ["IDs you relied on"]}',
        company_toolbox(g), max_steps=7)
    answer = final.get("answer") or str(final)
    ids = set(CITE.findall(answer))
    if isinstance(final.get("sources"), list):
        ids |= {s for s in final["sources"] if isinstance(s, str)}
    cards = []
    for sid in sorted(ids):                       # verify every citation exists in the graph
        s = read_source(g, sid)
        if "error" not in s:
            cards.append(s)
    return {"answer": answer, "sources": cards, "trace": trace}
