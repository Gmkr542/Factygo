"use client";

import { useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const tabs = [
  ["verdict", "Verdict"],
  ["evidence", "Web Evidence"],
  ["sources", "Sources"],
  ["claim", "Claim"],
  ["analysis", "Analysis"],
];

function label(value) {
  return String(value || "").replaceAll("_", " ").toUpperCase();
}

function verdictTone(value) {
  const x = String(value || "").toUpperCase();
  if (x === "TRUE") return "good";
  if (x === "FALSE") return "bad";
  if (x.includes("MOSTLY") || x === "PARTLY_TRUE" || x === "MISLEADING") return "warn";
  return "neutral";
}

function confidenceTone(value) {
  const n = Number(value || 0);
  if (n >= 75) return "high";
  if (n >= 45) return "medium";
  return "low";
}

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("verdict");

  async function investigate() {
    const claim = text.trim();
    if (!claim) return;

    setLoading(true);
    setResult(null);
    setTab("verdict");

    try {
      const response = await fetch(`${API}/api/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: claim }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Investigation failed.");
      setResult(data);
    } catch (error) {
      setResult({ error: error.message || "Could not connect to Factygo API." });
    } finally {
      setLoading(false);
    }
  }

  const evidence = result?.evidence || [];
  const sources = result?.sources || [];
  const supporting = useMemo(
    () => evidence.filter(e => String(e.stance).toLowerCase() === "supporting"),
    [evidence]
  );
  const contradicting = useMemo(
    () => evidence.filter(e => String(e.stance).toLowerCase() === "contradicting"),
    [evidence]
  );
  const contextual = useMemo(
    () => evidence.filter(e => String(e.stance).toLowerCase() === "contextual"),
    [evidence]
  );
  const domains = new Set(sources.map(s => s.domain).filter(Boolean)).size;
  const confidence = Number(result?.confidence || 0);
  const noResults = result && !result.error && !evidence.length && !sources.length;

  return (
    <main className="appShell">
      <div className="topBar">
        <div className="brandMark"><span className="brandDot" />FACTYGO</div>
        <span className="topTag">EVIDENCE-FIRST INVESTIGATION</span>
      </div>

      <header className="hero">
        <div className="eyebrow">AI RESEARCH WORKSPACE</div>
        <h1>Investigate claims.<br /><span>Follow the evidence.</span></h1>
        <p>Research a claim across the web, inspect the evidence, and see how the conclusion was reached.</p>
      </header>

      <section className="searchCard">
        <div className="searchLabelRow">
          <label htmlFor="claim">What do you want to investigate?</label>
          <span>TEXT INPUT</span>
        </div>
        <textarea
          id="claim"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") investigate();
          }}
          placeholder="e.g. Is Congress the central government in India in 2026?"
          rows={4}
          disabled={loading}
        />
        <div className="searchFooter">
          <span className="hint">Attachments are optional · Ctrl/Cmd + Enter to investigate</span>
          <button className="primaryButton" onClick={investigate} disabled={loading || !text.trim()}>
            {loading ? <><span className="spinner" /> Researching…</> : <>Investigate <span>→</span></>}
          </button>
        </div>
      </section>

      {loading && (
        <section className="loadingCard">
          <div className="loadingIcon"><span className="spinner dark" /></div>
          <div>
            <strong>Investigating claim</strong>
            <p>Searching the web and evaluating available evidence…</p>
          </div>
        </section>
      )}

      {result?.error && (
        <section className="stateCard errorState">
          <div className="stateIcon">!</div>
          <div>
            <strong>Investigation failed</strong>
            <p>{result.error}</p>
            <button className="secondaryButton" onClick={investigate}>Try again</button>
          </div>
        </section>
      )}

      {result && !result.error && (
        <section className="investigationCard">
          <div className="resultHero">
            <div className="verdictBlock">
              <div className={`verdictBadge ${verdictTone(result.verdict)}`}>
                <span className="statusDot" />
                {label(result.verdict)}
              </div>
              <h2>{result.explanation || "Factygo completed the investigation."}</h2>
              <div className="resultMeta">
                <span>{label(result.status || "complete")}</span>
                <span>•</span>
                <span>{domains} independent {domains === 1 ? "domain" : "domains"}</span>
              </div>
            </div>
            <div className={`confidenceMeter ${confidenceTone(confidence)}`}>
              <div className="confidenceRing" style={{ "--confidence": `${confidence}%` }}>
                <div><strong>{confidence}</strong><small>%</small></div>
              </div>
              <span>CONFIDENCE</span>
            </div>
          </div>

          <nav className="tabs" aria-label="Investigation sections">
            {tabs.map(([id, name]) => (
              <button
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => setTab(id)}
              >
                {name}
                {id === "evidence" && <em>{evidence.length}</em>}
                {id === "sources" && <em>{sources.length}</em>}
              </button>
            ))}
          </nav>

          <div className="panel">
            {tab === "verdict" && (
              <div className="panelContent">
                <div className="panelHeader">
                  <div>
                    <span className="sectionKicker">CONCLUSION</span>
                    <h3>Verdict</h3>
                  </div>
                </div>

                {noResults ? (
                  <div className="emptyState">
                    <div className="emptyIcon">?</div>
                    <h4>No sufficiently relevant evidence</h4>
                    <p>Factygo could not retrieve enough reliable web evidence to determine whether this claim is true or false. It will not invent a verdict.</p>
                    <button className="secondaryButton" onClick={investigate}>Search again</button>
                  </div>
                ) : (
                  <>
                    <p className="lead">{result.explanation || "No explanation was returned."}</p>
                    <div className="summaryGrid">
                      <div><span>SUPPORTING</span><strong>{supporting.length}</strong></div>
                      <div><span>CONTRADICTING</span><strong>{contradicting.length}</strong></div>
                      <div><span>CONTEXT</span><strong>{contextual.length}</strong></div>
                      <div><span>SOURCES</span><strong>{sources.length}</strong></div>
                    </div>
                    <div className="quickInsight">
                      <span className="insightIcon">i</span>
                      <div><strong>Evidence overview</strong><p>{supporting.length ? `${supporting.length} supporting item${supporting.length === 1 ? "" : "s"} found.` : "No direct supporting evidence found."} {contradicting.length ? `${contradicting.length} contradiction${contradicting.length === 1 ? "" : "s"} detected.` : "No direct contradiction detected."}</p></div>
                    </div>
                  </>
                )}
              </div>
            )}

            {tab === "evidence" && (
              <div className="panelContent">
                <div className="panelHeader">
                  <div><span className="sectionKicker">WEB RESEARCH</span><h3>Evidence</h3></div>
                  <span className="countPill">{evidence.length} items</span>
                </div>
                {evidence.length ? (
                  <div className="evidenceList">
                    {evidence.map((e, i) => (
                      <article className="evidenceCard" key={e.id || i}>
                        <div className="cardTop">
                          <span className={`stance ${String(e.stance).toLowerCase()}`}>{label(e.stance)}</span>
                          <div className="metricPills">
                            {e.relevance != null && <span>Relevance <b>{e.relevance}%</b></span>}
                            {e.strength != null && <span>Strength <b>{e.strength}%</b></span>}
                          </div>
                        </div>
                        <p className="quote">“{e.excerpt}”</p>
                        {e.reason && <p className="reason">{e.reason}</p>}
                        {e.source_url && <a className="sourceLink" href={e.source_url} target="_blank" rel="noreferrer">Open original source <span>↗</span></a>}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="emptyState compact"><div className="emptyIcon">⌕</div><h4>No web evidence</h4><p>No sufficiently relevant evidence was retrieved.</p></div>
                )}
              </div>
            )}

            {tab === "sources" && (
              <div className="panelContent">
                <div className="panelHeader">
                  <div><span className="sectionKicker">WEB RESEARCH</span><h3>Sources</h3></div>
                  <span className="countPill">{sources.length} sources</span>
                </div>
                {sources.length ? (
                  <div className="sourceList">
                    {sources.map((s, i) => (
                      <article className="sourceCard" key={s.url || i}>
                        <div className="sourceIcon">↗</div>
                        <div className="sourceMain">
                          <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a>
                          <span>{s.domain || "Unknown domain"}</span>
                        </div>
                        <div className="sourceMeta">
                          {s.source_tier && <span>Tier {s.source_tier}</span>}
                          {s.source_score != null && <strong>{Math.round(s.source_score * 100)}/100</strong>}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="emptyState compact"><div className="emptyIcon">◎</div><h4>No sources retrieved</h4><p>Factygo has no sources to display for this investigation.</p></div>
                )}
              </div>
            )}

            {tab === "claim" && (
              <div className="panelContent">
                <span className="sectionKicker">CLAIM UNDERSTANDING</span>
                <h3>Claim</h3>
                <div className="claimBox">{result.claim || text}</div>
                {result.claim_analysis && (
                  <div className="detailGrid">
                    <div><span>SUBJECT</span><b>{result.claim_analysis.subject || "Unknown"}</b></div>
                    <div><span>JURISDICTION</span><b>{result.claim_analysis.jurisdiction || "Unknown"}</b></div>
                    <div><span>YEAR</span><b>{result.claim_analysis.year || "Not specified"}</b></div>
                    <div><span>TYPE</span><b>{label(result.claim_analysis.claim_type || "Unknown")}</b></div>
                  </div>
                )}
                <h4>Claim breakdown</h4>
                {result.claims?.length ? <ol className="claims">{result.claims.map(c => <li key={c.id}>{c.text}</li>)}</ol> : <p className="muted">No additional decomposition returned.</p>}
              </div>
            )}

            {tab === "analysis" && (
              <div className="panelContent">
                <span className="sectionKicker">INVESTIGATION INTELLIGENCE</span>
                <h3>Analysis</h3>
                <div className="detailGrid four">
                  <div><span>SUPPORTING</span><b>{supporting.length}</b></div>
                  <div><span>CONTRADICTING</span><b>{contradicting.length}</b></div>
                  <div><span>CONTEXTUAL</span><b>{contextual.length}</b></div>
                  <div><span>INDEPENDENT DOMAINS</span><b>{domains}</b></div>
                </div>
                {result.evidence_analysis && (
                  <div className="analysisNote">
                    <strong>Corroboration</strong>
                    <p>{result.evidence_analysis.supporting_domains?.length || 0} supporting domains · {result.evidence_analysis.contradicting_domains?.length || 0} contradicting domains</p>
                  </div>
                )}
                {result.methodology?.length > 0 && <><h4>Methodology</h4><ul className="method">{result.methodology.map((m, i) => <li key={i}>{m}</li>)}</ul></>}
              </div>
            )}
          </div>
        </section>
      )}

      <footer><span>FACTYGO</span> · Evidence-first AI investigation · Evidence over assumption</footer>
    </main>
  );
}
