"""Tiny Graphviz (DOT) helpers. Streamlit renders DOT natively via st.graphviz_chart."""
from config import q

GREEN, YELLOW, RED, GREY, BLUE, AMBER = "#bbf7d0", "#fef08a", "#fecaca", "#e5e7eb", "#e0e7ff", "#fde68a"


def _esc(s):
    return str(s).replace('"', "'")


def edges_dot(edges, highlight=(), colors=None, rankdir="LR"):
    colors = colors or {}
    nodes = []
    for e in edges:
        for n in e[:2]:
            if n not in nodes:
                nodes.append(n)
    out = ["digraph G {", f"rankdir={rankdir};",
           'node [shape=box, style="rounded,filled", color="#6366f1", fontname="Helvetica"];',
           'edge [color="#94a3b8", fontname="Helvetica", fontsize=10];']
    for n in nodes:
        fill = colors.get(n, AMBER if n in highlight else BLUE)
        out.append(f'"{_esc(n)}" [fillcolor="{fill}"];')
    for e in edges:
        label = f' [label="{_esc(e[2])}"]' if len(e) > 2 and e[2] else ""
        out.append(f'"{_esc(e[0])}" -> "{_esc(e[1])}"{label};')
    out.append("}")
    return "\n".join(out)


def path_dot(names):
    """A linear path, e.g. a study order. Arrows point in the order to study."""
    return edges_dot([(names[i], names[i + 1]) for i in range(len(names) - 1)], highlight=set(names))


def curriculum_dot(g, uid, subject):
    """Prerequisite map for one subject, coloured by the student's mastery. Arrows: prerequisite -> topic."""
    in_subject = {r[0] for r in q(g, "MATCH (:Subject {name:$s})-[:HAS_TOPIC]->(t:Topic) RETURN t.name", s=subject)}
    scores = {r[0]: r[1] for r in q(g, "MATCH (:User {id:$uid})-[k:KNOWS_TOPIC]->(t:Topic) RETURN t.name, k.score", uid=uid)}
    edges = [(b, a) for a, b in
             [(r[0], r[1]) for r in q(g, "MATCH (a:Topic)-[:REQUIRES]->(b:Topic) RETURN a.name, b.name")]
             if a in in_subject or b in in_subject]
    colors = {}
    for a, b in edges:
        for n in (a, b):
            s = scores.get(n)
            colors[n] = GREY if s is None else RED if s < 50 else YELLOW if s < 75 else GREEN
    return edges_dot(edges, colors=colors, rankdir="TB")


def system_dot(g):
    rows = q(g, "MATCH (a:System)-[:DEPENDS_ON]->(b:System) RETURN a.name, b.name")
    return edges_dot([(r[0], r[1], "depends on") for r in rows])


def dots_from_trace(trace):
    """Turn what the Company Brain agent actually looked at into diagrams (the 'path behind the answer')."""
    dots = []
    for t in trace:
        res = t.get("result")
        if not isinstance(res, dict) or "error" in res:
            continue
        if t["tool"] == "impact_of_outage" and res.get("edges"):
            dots.append(("Blast radius if " + res["system"] + " goes down",
                         edges_dot([(a, b, "depends on") for a, b in res["edges"]], highlight={res["system"]})))
        elif t["tool"] == "decision_trace":
            edges = []
            for m in res.get("matches", []):
                me = f'{m["id"]}: {m["title"][:40]}'
                for o in m.get("supersedes", []):
                    edges.append((me, f'{o["id"]}: {o["title"][:40]}', "supersedes"))
                for s in m.get("sources", []):
                    edges.append((me, s["id"], "recorded in"))
            if edges:
                dots.append(("Decision trace", edges_dot(edges)))
        elif t["tool"] == "who_knows" and res.get("experts"):
            edges = [(e["person"], res["entity"], f'{e["sources_contributed"]} sources'
                      + (" · owner" if e["is_current_owner"] else "")) for e in res["experts"]]
            dots.append(("Who knows about " + res["entity"], edges_dot(edges, highlight={res["entity"]})))
    return dots
