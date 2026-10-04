const snapshot = {
  generatedAt: "2026-10-04 16:03 UTC",
  css: {
    projects: 379,
    active: 59,
    completed: 320,
    actions: 66,
    institutions: 57,
    customers: 196,
    topInstitutions: [
      ["Yonsei Univ.", 88],
      ["Ewha Univ.", 54],
      ["Kyungpook National Univ.", 33],
      ["AgingLab", 18],
      ["KAIST", 14],
      ["Konkuk Univ.", 13],
      ["ChungAng Univ.", 12],
      ["Jeju Univ.", 10],
      ["Gyeongsang National Univ.", 8],
      ["AiBiotics", 7],
    ],
    services: [
      ["mRNA-Seq", 183],
      ["PMP", 57],
      ["Amplicon", 33],
      ["PML", 23],
      ["Proteomics", 16],
      ["Microbial WGS", 11],
      ["Metagenome", 8],
      ["Animal WGS", 7],
      ["Plant WGS", 6],
      ["Metabolomics", 6],
      ["WGS - Unclassified", 6],
      ["Human WGS", 4],
      ["Other", 4],
    ],
  },
  ckd: {
    stages: 6,
    seedGenes: 9,
    evidenceGenes: 9,
    coverage: {
      "Stage4 EAS": "not in Drive",
      "KoGES": "not in Drive",
      "Thesis-ready": "not in Drive",
    },
    stagesList: [
      ["stage1", "20 files", "9.5 MB", "2026-09-16"],
      ["stage2", "7 files", "21.6 KB", "2026-09-16"],
      ["stage2b_coloc", "32 files", "20.2 MB", "2026-09-21"],
      ["stage2c_susie", "23 files", "10.0 MB", "2026-09-21"],
      ["stage3a_kidney", "7 files", "223.4 KB", "2026-09-21"],
      ["stage3b_celltype", "4 files", "34.6 KB", "2026-09-22"],
    ],
    genes: [
      { gene:"ACP1", anchor:"rs11553746", eurP:"3.04e-10", easP:"0.0333", coloc:0.9255, susie:0.9087, status:"ABF_and_SuSiE_shared_signal", cell:"collecting duct principal", compartment:"renal epithelial" },
      { gene:"CPVL", anchor:"rs34219043", eurP:"9.70e-05", easP:"0.221", coloc:0.6619, susie:null, status:"unresolved", cell:"cDC", compartment:"immune" },
      { gene:"F12", anchor:"rs1801020", eurP:"2.69e-05", easP:"1.93e-14", coloc:0.0000, susie:0.000011, status:"unresolved", cell:"proximal tubule", compartment:"renal epithelial" },
      { gene:"GSTA1", anchor:"rs6458871", eurP:"1.22e-08", easP:"0.546", coloc:0.8164, susie:0.7704, status:"ABF_not_confirmed_by_SuSiE", cell:"proximal tubule", compartment:"renal epithelial" },
      { gene:"GSTA3", anchor:"rs2749005", eurP:"2.01e-09", easP:"0.584", coloc:0.9520, susie:0.9649, status:"ABF_and_SuSiE_shared_signal", cell:"loop of Henle", compartment:"renal epithelial" },
      { gene:"HLA-E", anchor:"rs2523594", eurP:"3.44e-07", easP:"0.555", coloc:0.000000115, susie:0.000210, status:"unresolved", cell:"vascular endothelial", compartment:"vascular" },
      { gene:"INHBC", anchor:"rs3741414", eurP:"1.47e-20", easP:"0.0644", coloc:0.9513, susie:0.0000000000000344, status:"ABF_not_confirmed_by_SuSiE", cell:"proximal tubule", compartment:"renal epithelial" },
      { gene:"SDCCAG8", anchor:"rs953492", eurP:"5.68e-16", easP:"0.0872", coloc:0.97945, susie:0.97941, status:"ABF_and_SuSiE_shared_signal", cell:"macrophages", compartment:"immune" },
      { gene:"UMOD", anchor:"rs77924615", eurP:"1.07e-221", easP:"2.26e-47", coloc:0.0000, susie:null, status:"SuSiE_nonconverged_or_failed", cell:"loop of Henle", compartment:"renal epithelial" },
    ],
  },
};

function Metric({label,value,sub}) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{sub && <small>{sub}</small>}</div>;
}
function Badge({children,tone="neutral"}) {
  return <span className={"badge "+tone}>{children}</span>;
}
function statusTone(status) {
  if (status === "ABF_and_SuSiE_shared_signal") return "good";
  if (status === "ABF_not_confirmed_by_SuSiE") return "warn";
  if (status === "SuSiE_nonconverged_or_failed") return "bad";
  return "neutral";
}
function compactStatus(status) {
  return {
    ABF_and_SuSiE_shared_signal:"Shared signal",
    ABF_not_confirmed_by_SuSiE:"ABF only / mixed",
    SuSiE_nonconverged_or_failed:"SuSiE failed",
    unresolved:"Unresolved",
  }[status] || status;
}
function H4Bar({value}) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, Number(value)));
  return <div className="bar"><span style={{width:(v*100)+"%"}} /></div>;
}

export default function Page() {
  const {css,ckd}=snapshot;
  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">MASTEROS · PRIVATE RESEARCH SNAPSHOT</p>
          <h1>Research × CSS Intelligence</h1>
          <p className="lede">Google Drive → Colab → Obsidian → Web. 고객 개인정보 없이 연구 진행상황과 CSS 집계만 표시합니다.</p>
        </div>
        <div className="stamp">Snapshot<br/><b>{snapshot.generatedAt}</b></div>
      </header>

      <nav>
        <a href="#overview">Overview</a>
        <a href="#ckd">CKD</a>
        <a href="#css">CSS Summary</a>
      </nav>

      <section id="overview">
        <div className="sectionHead"><div><p className="eyebrow">OVERVIEW</p><h2>현재 상태</h2></div><Badge tone="good">Drive refresh verified</Badge></div>
        <div className="metrics six">
          <Metric label="CSS projects" value={css.projects} sub={css.active+" active"} />
          <Metric label="CSS completed" value={css.completed} />
          <Metric label="Action queue" value={css.actions} />
          <Metric label="CKD stages" value={ckd.stages} />
          <Metric label="CKD candidate genes" value={ckd.seedGenes} sub="seed = stage2 candidates" />
          <Metric label="Canonical institutions" value={css.institutions} sub="76 raw → 57" />
        </div>
        <div className="notice">
          <b>Data boundary</b>
          <span>웹에는 고객명, 이메일, 견적/가격, 개인 메모를 넣지 않았습니다. CSS는 집계만, 연구는 9-gene evidence snapshot만 노출합니다.</span>
        </div>
      </section>

      <section id="ckd">
        <div className="sectionHead">
          <div><p className="eyebrow">RESEARCH · CKD</p><h2>9-gene evidence panel</h2></div>
          <div className="badges"><Badge tone="good">9/9 seed genes</Badge><Badge>6 Drive stages</Badge></div>
        </div>

        <div className="coverage">
          {Object.entries(ckd.coverage).map(([k,v])=><div key={k}><span>{k}</span><Badge tone="warn">{v}</Badge></div>)}
        </div>

        <div className="geneGrid">
          {ckd.genes.map(g=>(
            <article className="geneCard" key={g.gene}>
              <div className="geneTop"><div><h3>{g.gene}</h3><code>{g.anchor}</code></div><Badge tone={statusTone(g.status)}>{compactStatus(g.status)}</Badge></div>
              <div className="geneStats">
                <div><span>ABF PP.H4</span><b>{g.coloc < 0.0001 ? g.coloc.toExponential(2) : g.coloc.toFixed(3)}</b><H4Bar value={g.coloc}/></div>
                <div><span>SuSiE H4</span><b>{g.susie == null ? "NA" : (g.susie < 0.0001 ? g.susie.toExponential(2) : g.susie.toFixed(3))}</b><H4Bar value={g.susie}/></div>
              </div>
              <dl>
                <div><dt>EUR eGFR P</dt><dd>{g.eurP}</dd></div>
                <div><dt>EAS eGFR P</dt><dd>{g.easP}</dd></div>
                <div><dt>Kidney / cell</dt><dd>{g.cell}</dd></div>
                <div><dt>Compartment</dt><dd>{g.compartment}</dd></div>
              </dl>
            </article>
          ))}
        </div>

        <div className="tableWrap">
          <table>
            <thead><tr><th>Stage</th><th>Files</th><th>Size</th><th>Latest source</th></tr></thead>
            <tbody>{ckd.stagesList.map(r=><tr key={r[0]}>{r.map((x,i)=><td key={i}>{x}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </section>

      <section id="css">
        <div className="sectionHead"><div><p className="eyebrow">SALES · CSS</p><h2>Aggregate portfolio view</h2></div><Badge>no PII</Badge></div>
        <div className="metrics four">
          <Metric label="Projects" value={css.projects} sub={css.active+" active / "+css.completed+" completed"} />
          <Metric label="Institutions" value={css.institutions} />
          <Metric label="Customers" value={css.customers} />
          <Metric label="Open actions" value={css.actions} />
        </div>

        <div className="split">
          <div className="panel">
            <h3>Top institutions</h3>
            {css.topInstitutions.map(([name,n])=><div className="rankRow" key={name}><span>{name}</span><b>{n}</b></div>)}
          </div>
          <div className="panel">
            <h3>Service taxonomy</h3>
            {css.services.map(([name,n])=><div className="rankRow" key={name}><span>{name}</span><b>{n}</b></div>)}
          </div>
        </div>
      </section>

      <footer>
        <b>MasterOS</b>
        <span>Generated knowledge layer · source systems remain authoritative</span>
      </footer>
    </main>
  );
}
