"""Mechanical, interface-specific diagnostics, not semantic scoring."""


def graph_diagnostics(rows):
    parents = {r["id"]: r["supersedes"] for r in rows}
    cycles = set()
    for start in parents:
        path, visited, current = [], {}, start
        while current is not None and current in parents:
            if current in visited:
                cycles.update(path[visited[current]:])
                break
            visited[current] = len(path)
            path.append(current)
            current = parents[current]
    return dict(self_edges=sorted(i for i, p in parents.items() if i == p),
                cycle_nodes=sorted(cycles),
                dangling_predecessors=sorted(i for i, p in parents.items() if p is not None and p not in parents))


def effect(outcome, requested, public, physical, cold_public):
    if any(v is None for v in (public, physical, cold_public)):
        return "UNKNOWN"
    if outcome != "return":
        return "API_EXCEPTION"
    observed = [requested in values for values in (public, physical, cold_public)]
    if len(set(observed)) != 1:
        return "OBSERVATION_DISAGREEMENT"
    return "REQUESTED_VALUE_VISIBLE" if observed[0] else "SUCCESS_WITH_REQUESTED_VALUE_UNAVAILABLE"
