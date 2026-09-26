"""Knowledge graph view for a project: included papers, the methods / datasets /
tasks their notes mention, and citation links among them. Built from the global
Paper cache, so it gets richer as more projects cover the same field."""

import re
from collections import defaultdict

from sqlmodel import Session, select

from .db import Paper, ProjectPaper, engine

ENTITY_KINDS = {"methods": "method", "datasets": "dataset", "tasks": "task"}
MAX_ENTITIES = 70


def _norm(name: str) -> str:
    """Loose key so 'Protein language models' and 'protein language model' merge."""
    words = re.sub(r"[^a-z0-9+]+", " ", name.lower()).split()
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words)


def project_graph(project_id: str) -> dict:
    with Session(engine) as s:
        rows = s.exec(
            select(ProjectPaper, Paper)
            .join(Paper, Paper.id == ProjectPaper.paper_id)
            .where(ProjectPaper.project_id == project_id, ProjectPaper.included)
        ).all()

    papers = {p.id: (pp, p) for pp, p in rows}
    by_s2 = {p.s2_id: p.id for _, p in papers.values() if p.s2_id}

    # Entities shared by at least two papers carry the structure; singletons are noise.
    mentions: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for pid, (_, p) in papers.items():
        for field, kind in ENTITY_KINDS.items():
            for name in (p.notes or {}).get(field, []):
                if not (n := _norm(name)):
                    continue
                key = f"{kind}:{n}"
                mentions[key].add(pid)
                labels.setdefault(key, name)
    shared = sorted((k for k, v in mentions.items() if len(v) >= 2), key=lambda k: -len(mentions[k]))[:MAX_ENTITIES]

    nodes = [
        {
            "id": pid,
            "kind": "paper",
            "label": p.title,
            "year": p.year,
            "citations": p.citation_count,
            "relevance": pp.relevance,
        }
        for pid, (pp, p) in papers.items()
    ]
    nodes += [{"id": k, "kind": k.split(":", 1)[0], "label": labels[k], "count": len(mentions[k])} for k in shared]

    links = [{"source": pid, "target": k, "kind": "mentions"} for k in shared for pid in mentions[k]]
    for pid, (_, p) in papers.items():
        for ref in p.references or []:
            if (target := by_s2.get(ref)) and target != pid:
                links.append({"source": pid, "target": target, "kind": "cites"})
    return {"nodes": nodes, "links": links}
