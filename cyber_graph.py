"""Builds the security layer inside the Nimbus Labs graph and offers the basic investigation queries."""
import config
import company_brain as cb
from config import q
import cyber_data as cd


def is_loaded(g):
    try:
        return q(g, "MATCH (a:AIAgent) RETURN count(a)")[0][0] > 0
    except Exception:
        return False


def reset_security_layer(g):
    q(g, "MATCH (a:AIAgent) DETACH DELETE a")
    q(g, "MATCH (r:Resource) DETACH DELETE r")


def load_security_layer(g):
    """Adds AI agents, resources, permissions, trust chains and access history to the company graph."""
    if not cb.is_loaded(g):
        cb.load_sample(g)
    if is_loaded(g):
        return "already loaded"

    for name, kind, sens, system in cd.RESOURCES:
        q(g, "MERGE (r:Resource {name:$n}) SET r.kind=$k, r.sensitivity=$s", n=name, k=kind, s=sens)
        q(g, "MATCH (r:Resource {name:$n}), (s:System {name:$sys}) MERGE (r)-[:STORED_IN]->(s)", n=name, sys=system)

    for name, purpose, status, owner, system, created in cd.AGENTS:
        q(g, "MERGE (a:AIAgent {name:$n}) SET a.purpose=$p, a.status=$s, a.created=$c",
          n=name, p=purpose, s=status, c=created)
        q(g, "MATCH (a:AIAgent {name:$n}), (s:System {name:$sys}) MERGE (a)-[:RUNS_ON]->(s)", n=name, sys=system)
        if owner:
            q(g, "MATCH (a:AIAgent {name:$n}), (p:Person {name:$o}) MERGE (a)-[:DEPLOYED_BY]->(p)", n=name, o=owner)

    for agent, res, scope, since in cd.GRANTS:
        q(g, "MATCH (a:AIAgent {name:$a}), (r:Resource {name:$r}) MERGE (a)-[x:GRANTED]->(r) "
             "SET x.scope=$s, x.since=$d", a=agent, r=res, s=scope, d=since)

    for a, b in cd.DELEGATIONS:
        q(g, "MATCH (x:AIAgent {name:$a}), (y:AIAgent {name:$b}) MERGE (x)-[:DELEGATES_TO]->(y)", a=a, b=b)

    for agent, res, ts, action, volume in cd.EVENTS:
        q(g, "MATCH (a:AIAgent {name:$a}), (r:Resource {name:$r}) "
             "CREATE (a)-[:ACCESSED {ts:$ts, hour:$h, action:$act, volume:$v}]->(r)",
          a=agent, r=res, ts=ts, h=int(ts[11:13]), act=action, v=volume)
    return "loaded"


# ---------------------------------------------------------------- investigation queries
def find_ungranted_access(g):
    """Agents that touched something they were never officially given."""
    rows = q(g, "MATCH (a:AIAgent)-[x:ACCESSED]->(r:Resource) "
                "OPTIONAL MATCH (a)-[gr:GRANTED]->(r) "
                "WITH a, r, x, gr WHERE gr IS NULL "
                "RETURN a.name, r.name, r.sensitivity, count(x), sum(x.volume), min(x.hour) "
                "ORDER BY r.sensitivity DESC, sum(x.volume) DESC")
    return [{"agent": r[0], "resource": r[1], "sensitivity": r[2], "times": r[3],
             "records": r[4], "earliest_hour": r[5]} for r in rows]


def find_trust_chains(g):
    """Agents that gain power through other agents, even though they were never granted it directly."""
    rows = q(g, "MATCH p=(a:AIAgent)-[:DELEGATES_TO*1..5]->(b:AIAgent)-[:GRANTED]->(r:Resource) "
                "OPTIONAL MATCH (a)-[d:GRANTED]->(r) "
                "WITH p, a, r, d WHERE d IS NULL "
                "RETURN a.name, r.name, r.sensitivity, [n IN nodes(p) | n.name]")
    return [{"agent": r[0], "inherited_resource": r[1], "sensitivity": r[2], "chain": r[3]} for r in rows]


def find_orphan_agents(g):
    """Agents with no human owner."""
    rows = q(g, "MATCH (a:AIAgent) OPTIONAL MATCH (a)-[:DEPLOYED_BY]->(p:Person) "
                "WITH a, p WHERE p IS NULL RETURN a.name, a.status")
    return [{"agent": r[0], "status": r[1]} for r in rows]


if __name__ == "__main__":
    g = config.company_graph("nimbus")
    print("Building the crime scene:", load_security_layer(g))
    ungranted = find_ungranted_access(g)
    chains = find_trust_chains(g)
    orphans = find_orphan_agents(g)

    print("\nAgents that touched things they were never given:")
    for u in ungranted:
        print(f"  - {u['agent']} -> {u['resource']} ({u['records']} records, sensitivity {u['sensitivity']})")
    print("\nPower gained through chains of trust:")
    for c in chains:
        print(f"  - {' -> '.join(c['chain'])}")
    print("\nAgents with no human owner:")
    for o in orphans:
        print(f"  - {o['agent']} ({o['status']})")

    ok = (
        {u["agent"] for u in ungranted} == cd.ANSWER_KEY["ungranted_agents"]
        and any(c["agent"] == cd.ANSWER_KEY["chain_agent"] for c in chains)
        and {o["agent"] for o in orphans} == cd.ANSWER_KEY["orphan_agents"]
    )
    print("\nALL 3 INCIDENTS CAN BE FOUND" if ok else "\nSOMETHING IS OFF: paste this output to me")
