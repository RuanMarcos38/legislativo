"""Source-backed per-person activity. No ratings or inferred individual votes."""
from datetime import date
from .db import serialize
from .automatic import PROJECT_TYPES,author_stream

def dashboard(db,key,start="",end="",page=1,size=20,category="all"):
    person=db.execute("SELECT * FROM records WHERE id=? AND kind='person'",(key,)).fetchone()
    if not person:raise KeyError(key)
    if person["source"] not in {"camara","senado"}:raise ValueError("Fonte não integrada")
    if not 1<=page<=100000 or not 1<=size<=100:raise ValueError("Paginação inválida")
    for value in (start,end):
        if value:date.fromisoformat(value)
    if start and end and start>end:raise ValueError("Período inválido")
    if category not in {"all","projects","approved","norms"}:raise ValueError("Categoria inválida")
    sid=author_stream(db,key,priority=0);db.commit()
    stream=dict(db.execute("SELECT * FROM sync_streams WHERE key=?",(sid,)).fetchone())
    clauses=["a.person_id=?"];args=[key]
    if start:clauses.append("substr(f.presented_at,1,10)>=?");args.append(start)
    if end:clauses.append("substr(f.presented_at,1,10)<=?");args.append(end)
    query="""SELECT r.*,a.relation,a.source_url authorship_source,a.collected_at authorship_collected_at,
      f.type proposal_type,f.presented_at,f.status proposal_status,f.urn,f.norm_reported,f.detail_checked_at,
      f.history_checked_at,f.authors_checked_at,
      EXISTS(SELECT 1 FROM approval_evidence e WHERE e.proposal_id=r.id) has_approval
      FROM authorships a JOIN records r ON r.id=a.proposal_id JOIN proposal_facts f ON f.proposal_id=r.id
      WHERE """+" AND ".join(clauses)
    rows=db.execute(query+" ORDER BY f.presented_at DESC,r.id",args).fetchall()
    projects=[r for r in rows if r["proposal_type"] in PROJECT_TYPES]
    approved=[r for r in projects if r["has_approval"]]
    norms=[r for r in projects if r["norm_reported"]]
    checked=[r for r in projects if r["history_checked_at"]]
    unknown_dates=db.execute("""SELECT COUNT(*) FROM authorships a JOIN proposal_facts f ON f.proposal_id=a.proposal_id
       WHERE a.person_id=? AND (f.presented_at IS NULL OR f.presented_at='')""",(key,)).fetchone()[0]
    selected=rows if category=="all" else projects if category=="projects" else approved if category=="approved" else norms
    items=[]
    for row in selected[(page-1)*size:page*size]:
        r=serialize(row)
        r["evidence"]=[dict(ev) for ev in db.execute("SELECT code,description,event_date,source_url,collected_at FROM approval_evidence WHERE proposal_id=? ORDER BY event_date",(row["id"],))]
        items.append(r)
    groups={}
    for row in rows:
        year=(row["presented_at"] or "")[:4] or "Sem data"
        group=groups.setdefault(year,dict(year=year,proposals=0,projects=0,approved=0))
        group["proposals"]+=1
        if row["proposal_type"] in PROJECT_TYPES:
            group["projects"]+=1;group["approved"]+=int(row["has_approval"])
    statuses={}
    for row in rows:
        state=row["proposal_status"] or "Situação ainda não coletada"
        statuses[state]=statuses.get(state,0)+1
    vote_clauses=["person_id=?"];vote_args=[key]
    if start:vote_clauses.append("substr(vote_date,1,10)>=?");vote_args.append(start)
    if end:vote_clauses.append("substr(vote_date,1,10)<=?");vote_args.append(end)
    voting=[dict(r) for r in db.execute("SELECT choice,COUNT(*) count FROM nominal_votes WHERE "+" AND ".join(vote_clauses)+" GROUP BY choice",vote_args)] if person["source"]=="camara" else None
    return dict(voting=voting,person=serialize(person),period=dict(start=start,end=end,date_basis="Data de apresentação informada pela fonte; não o ano de renumeração."),
        metrics=dict(proposals=len(rows),projects=len(projects),other_proposals=len(rows)-len(projects),
          first_signatory=sum(r["relation"]=="first_signatory" for r in rows),
          coauthor=sum(r["relation"]=="coauthor" for r in rows),
          authorship_unspecified=sum(r["relation"]=="author_unspecified" for r in rows),
          projects_with_approval_stage=len(approved),projects_history_checked=len(checked),
          projects_history_pending=len(projects)-len(checked),norms_reported=len(norms),
          laws_publication_verified=None,implementation_verified=None,unknown_presentation_dates=unknown_dates),
        timeline=sorted(groups.values(),key=lambda r:r["year"]),statuses=statuses,
        sync=dict(state=stream["state"],pages=stream["pages"],items=stream["items"],
          completed_at=stream["completed_at"],last_success=stream["last_success"],
          scope=stream["scope"],error=None if stream["state"]=="running" else stream["error"],
          author_query_complete=stream["state"]=="idle" and bool(stream["completed_at"])),
        methodology=dict(project_types=sorted(PROJECT_TYPES),approval="Propostas distintas com evento estruturado de aprovação em alguma etapa; não aprovação final nem lei.",
          attribution="Autoria e coautoria não representam realização individual ou resultado de política pública.",
          completeness="Contagens observadas nos documentos coletados. Dados pendentes e falhas são exibidos; ausência de evidência não prova zero de atuação.",
          laws="Norma informada pela Casa não equivale a publicação conferida nem implementação. Aprovação de requerimento, parecer ou urgência não entra no indicador de projetos aprovados."),
        total=len(selected),page=page,size=size,items=items)
