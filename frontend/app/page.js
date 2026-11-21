"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const tabs = [
  ["verdict", "Verdict"],
  ["evidence", "Web Evidence"],
  ["sources", "Sources"],
  ["claim", "Claim"],
  ["analysis", "Analysis"],
  ["research", "Research"],
];

const SAMPLE_PROMPTS = [
  { text: "Lemon juice reduces diabetes", tag: "Health" },
  { text: "Drinking green tea prevents heart disease", tag: "Medical" },
  { text: "India's Chandrayaan-3 landed near the lunar south pole in August 2023", tag: "Space" },
  { text: "The Great Wall of China is visible from the Moon with the naked eye", tag: "Science" },
  { text: "Does intermittent fasting improve insulin sensitivity?", tag: "Question" },
  { text: "Antibiotics are effective against viral infections like the common cold", tag: "Medical" },
  { text: "Does India have the world's largest population?", tag: "Question" },
  { text: "Solar panels generate zero electricity on cloudy days", tag: "Energy" },
];

function label(value) {
  return String(value || "").replaceAll("_", " ").toUpperCase();
}

function verdictTone(value) {
  const x = String(value || "").toUpperCase();
  if (x === "TRUE") return "good";
  if (x === "FALSE") return "bad";
  if (x.includes("MOSTLY") || x === "PARTLY_TRUE" || x === "PARTLY TRUE" || x === "MISLEADING") return "warn";
  return "neutral";
}

function confidenceTone(value) {
  const n = Number(value || 0);
  if (n >= 75) return "high";
  if (n >= 45) return "medium";
  return "low";
}

function splitReport(explanation) {
  const raw = String(explanation || "").trim();
  if (!raw) {
    return {
      summary: "Factygo completed the investigation.",
      breakdown: "No detailed breakdown was returned.",
    };
  }
  const idx = raw.indexOf("Breakdown:");
  if (idx !== -1) {
    const summary = raw.slice(0, idx).trim();
    const breakdown = raw.slice(idx).trim();
    return {
      summary: summary || raw,
      breakdown: breakdown || raw,
    };
  }
  const sentences = raw.split(/(?<=[.!?])\s+/).filter(Boolean);
  if (sentences.length >= 2) {
    return {
      summary: sentences[0],
      breakdown: "Breakdown: " + sentences.slice(1).join(" "),
    };
  }
  return {
    summary: raw,
    breakdown: raw,
  };
}

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("verdict");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [shuffledPrompts, setShuffledPrompts] = useState(SAMPLE_PROMPTS);
  const searchBoxRef = useRef(null);

  function shuffleSuggestions() {
    const copy = [...SAMPLE_PROMPTS];
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    setShuffledPrompts(copy);
  }

  useEffect(() => {
    function handleOutsideClick(e) {
      if (searchBoxRef.current && !searchBoxRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const filteredSuggestions = useMemo(() => {
    const q = text.trim().toLowerCase();
    if (!q) return shuffledPrompts;
    const matches = shuffledPrompts.filter(item => item.text.toLowerCase().includes(q));
    return matches.length >= 3
      ? matches
      : [...matches, ...shuffledPrompts.filter(item => !item.text.toLowerCase().includes(q))];
  }, [text, shuffledPrompts]);

  async function investigate(overrideText) {
    const claim = (typeof overrideText === "string" ? overrideText : text).trim();
    if (!claim) return;

    setShowSuggestions(false);
    setLoading(true);
    setResult(null);
    setTab("verdict");

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 45000);
      let response;
      try {
        response = await fetch(API + "/api/investigate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: claim }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Investigation failed.");
      setResult(data);
    } catch (error) {
      setResult({
        error:
          error.name === "AbortError"
            ? "Research timed out. The web search provider may be unavailable right now."
            : error.message || "Could not connect to Factygo API.",
      });
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
  const domains = useMemo(() => {
    if (result?.evidence_analysis?.independent_domains != null && result.evidence_analysis.independent_domains > 0) {
      return result.evidence_analysis.independent_domains;
    }
    const hosts = new Set(
      sources
        .map(s => {
          if (s.domain) return s.domain;
          try {
            return new URL(s.url).hostname.replace(/^www\./, "");
          } catch {
            return "";
          }
        })
        .filter(Boolean)
    );
    return hosts.size;
  }, [result, sources]);

  const confidence = Number(result?.confidence || 0);
  const noResults = result && !result.error && !evidence.length && !sources.length;
  const { summary, breakdown } = useMemo(() => splitReport(result?.explanation), [result?.explanation]);

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

      <section className="searchCard" ref={searchBoxRef}>
        <div className="searchLabelRow">
          <label htmlFor="claim">What do you want to investigate?</label>
          <span>TEXT INPUT</span>
        </div>
        <div className="inputWrap">
          <textarea
            id="claim"
            value={text}
            onFocus={() => {
              shuffleSuggestions();
              setShowSuggestions(true);
            }}
            onKeyUp={e => {
              if (e.key === "Escape") {
                setShowSuggestions(false);
                return;
              }
              if (!(e.ctrlKey || e.metaKey) && e.key !== "Enter") {
                setShowSuggestions(true);
              }
            }}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => {
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") investigate();
            }}
            placeholder="Write your claim or question..."
            rows={2}
            disabled={loading}
          />
          {showSuggestions && !loading && (
            <div className="suggestionsDropdown" role="listbox" aria-label="Suggested claims and questions">
              <div className="suggestionsHeader">
                <span>SUGGESTED CLAIMS & QUESTIONS</span>
                <span>SCROLL FOR MORE</span>
              </div>
              <div className="suggestionsList">
                {filteredSuggestions.map((item, idx) => (
                  <button
                    type="button"
                    key={item.text + "-" + idx}
                    className="suggestionItem"
                    onClick={() => {
                      setText(item.text);
                      setShowSuggestions(false);
                    }}
                  >
                    <span>{item.text}</span>
                    <span className="suggestionTag">{item.tag}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="searchFooter">
          <span className="hint">Attachments are optional · Ctrl/Cmd + Enter to investigate</span>
          <button className="primaryButton" onClick={() => investigate()} disabled={loading || !text.trim()}>
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
            <button className="secondaryButton" onClick={() => investigate()}>Try again</button>
          </div>
        </section>
      )}

      {result && !result.error && (
        <section className="investigationCard">
          <div className="resultHero">
            <div className="verdictBlock">
              <div className={"verdictBadge " + verdictTone(result.verdict)}>
                <span className="verdictDot" />
                {label(result.verdict)}
              </div>
              <h2>{summary}</h2>
              <div className="metaLine">
                <span>{label(result.status || "complete")}</span>
                <span>•</span>
                <span>{domains} independent {domains === 1 ? "domain" : "domains"}</span>
              </div>
            </div>

            <div className={"confidenceMeter " + confidenceTone(confidence)}>
              <div className="confidenceRing" style={{ "--confidence": confidence + "%" }}>
                <div className="confidenceInner">{confidence}%</div>
              </div>
              <span className="confidenceLabel">CONFIDENCE</span>
            </div>
          </div>

          <nav className="tabBar" aria-label="Investigation sections">
            {tabs.map(([id, name]) => (
              <button
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => setTab(id)}
              >
                {name}
                {id === "evidence" ? " (" + evidence.length + ")" : ""}
                {id === "sources" ? " (" + sources.length + ")" : ""}
              </button>
            ))}
          </nav>

          {tab === "verdict" && (
            <div className="tabPanel">
              <div className="sectionHeader">
                <span className="sectionKicker">CONCLUSION</span>
                <h3>Verdict Breakdown</h3>
              </div>

              {noResults ? (
                <div className="emptyBox">
                  <div className="emptyIcon">?</div>
                  <strong>No sufficiently relevant evidence</strong>
                  <p>Factygo could not retrieve enough reliable web evidence to determine whether this claim is true or false. It will not invent a verdict.</p>
                  <button className="secondaryButton" onClick={() => investigate()}>Search again</button>
                </div>
              ) : (
                <>
                  <p className="leadText">{breakdown}</p>
                  <div className="statGrid">
                    <div className="statBox"><span>SUPPORTING</span><strong>{supporting.length}</strong></div>
                    <div className="statBox"><span>CONTRADICTING</span><strong>{contradicting.length}</strong></div>
                    <div className="statBox"><span>CONTEXT</span><strong>{contextual.length}</strong></div>
                    <div className="statBox"><span>SOURCES</span><strong>{sources.length}</strong></div>
                  </div>
                  <div className="infoNote">
                    <span className="infoBadge">i</span>
                    <div>
                      <strong>Evidence overview</strong>
                      <p>
                        {supporting.length
                          ? supporting.length + " supporting item" + (supporting.length === 1 ? "" : "s") + " found."
                          : "No direct supporting evidence found."}{" "}
                        {contradicting.length
                          ? contradicting.length + " contradiction" + (contradicting.length === 1 ? "" : "s") + " detected."
                          : "No direct contradiction detected."}
                      </p>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {tab === "evidence" && (
            <div className="tabPanel">
              <div className="sectionHeader">
                <span className="sectionKicker">WEB RESEARCH</span>
                <h3>Evidence ({evidence.length} items)</h3>
              </div>
              {evidence.length ? (
                <div className="cardStack">
                  {evidence.map((e, i) => (
                    <article className="evidenceCard" key={e.id || e.evidence_id || i}>
                      <div className="cardTopRow">
                        <span className={"stance " + String(e.stance).toLowerCase()}>{label(e.stance)}</span>
                        <div className="pillGroup">
                          {e.relevance != null && <span className="metaPill">Relevance {Math.round(Number(e.relevance) <= 1 ? Number(e.relevance) * 100 : Number(e.relevance))}%</span>}
                          {e.strength != null && <span className="metaPill">Strength {Math.round(Number(e.strength) <= 1 ? Number(e.strength) * 100 : Number(e.strength))}%</span>}
                        </div>
                      </div>
                      <blockquote className="excerptText">“{e.excerpt}”</blockquote>
                      {e.reason && <p className="reasonText">{e.reason}</p>}
                      {e.source_url && (
                        <a className="sourceLink" href={e.source_url} target="_blank" rel="noreferrer">
                          Open original source ↗
                        </a>
                      )}
                    </article>
                  ))}
                </div>
              ) : (
                <div className="emptyBox">
                  <div className="emptyIcon">⌕</div>
                  <strong>No web evidence</strong>
                  <p>No sufficiently relevant evidence was retrieved.</p>
                </div>
              )}
            </div>
          )}

          {tab === "sources" && (
            <div className="tabPanel">
              <div className="sectionHeader">
                <span className="sectionKicker">WEB RESEARCH</span>
                <h3>Sources ({sources.length} sources)</h3>
              </div>
              {sources.length ? (
                <div className="cardStack">
                  {sources.map((s, i) => {
                    let displayDomain = s.domain || "";
                    if (!displayDomain && s.url) {
                      try {
                        displayDomain = new URL(s.url).hostname.replace(/^www\./, "");
                      } catch {
                        displayDomain = "Unknown domain";
                      }
                    }
                    return (
                      <article className="sourceCard" key={s.url || i}>
                        <div className="sourceMain">
                          <a className="sourceTitle" href={s.url} target="_blank" rel="noreferrer">
                            {s.title || s.url} ↗
                          </a>
                          <span className="sourceDomain">{displayDomain || "Unknown domain"}</span>
                        </div>
                        <div className="pillGroup">
                          {s.source_tier && <span className="metaPill">Tier {s.source_tier}</span>}
                          {s.source_score != null && (
                            <span className="metaPill">{Math.round(s.source_score * 100)}/100</span>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="emptyBox">
                  <div className="emptyIcon">◎</div>
                  <strong>No sources retrieved</strong>
                  <p>Factygo has no sources to display for this investigation.</p>
                </div>
              )}
            </div>
          )}

          {tab === "claim" && (
            <div className="tabPanel">
              <div className="sectionHeader">
                <span className="sectionKicker">CLAIM UNDERSTANDING</span>
                <h3>Claim</h3>
              </div>
              <p className="leadText">{result.claim || text}</p>
              {result.claim_analysis && (
                <div className="statGrid">
                  <div className="statBox"><span>SUBJECT</span><strong>{result.claim_analysis.subject || result.claim_analysis.domain || "Unknown"}</strong></div>
                  <div className="statBox"><span>JURISDICTION</span><strong>{result.claim_analysis.jurisdiction || "Unknown"}</strong></div>
                  <div className="statBox"><span>YEAR</span><strong>{result.claim_analysis.year || "Not specified"}</strong></div>
                  <div className="statBox"><span>TYPE</span><strong>{label(result.claim_analysis.claim_type || result.claim_analysis.domain || "Unknown")}</strong></div>
                </div>
              )}
              <h4 className="subHeading">Claim breakdown</h4>
              {result.claims?.length ? (
                <ul className="cleanList">
                  {result.claims.map((c, idx) => (
                    <li key={c.id || idx}>{c.text}</li>
                  ))}
                </ul>
              ) : (
                <p className="mutedText">No additional decomposition returned.</p>
              )}
            </div>
          )}

          {tab === "research" && (
            <div className="tabPanel">
              <div className="sectionHeader">
                <span className="sectionKicker">RESEARCH PLAN</span>
                <h3>Framed questions</h3>
              </div>
              <p className="mutedText">Each question is researched independently. These raw answers are evidence inputs for the final synthesis, not separate verdicts.</p>
              <div className="cardStack">
                {(result.research_questions || []).map((q) => (
                  <article className="questionCard" key={q.id}>
                    <div className="cardTopRow">
                      <span className="qBadge">Q{q.id}</span>
                      <span className="metaPill">
                        {q.evidence_count} source{q.evidence_count === 1 ? "" : "s"} · {label(q.status)}
                      </span>
                    </div>
                    <h4>{q.question}</h4>
                    <p>{q.raw_answer || "No raw answer returned."}</p>
                    {q.sources?.length > 0 && (
                      <div className="pillGroup">
                        {q.sources.map((source, idx) => (
                          <a
                            key={source.url || idx}
                            className="sourceLink"
                            href={source.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {source.title || source.domain} ↗
                          </a>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </div>
          )}

          {tab === "analysis" && (
            <div className="tabPanel">
              <div className="sectionHeader">
                <span className="sectionKicker">INVESTIGATION INTELLIGENCE</span>
                <h3>Analysis</h3>
              </div>
              <div className="statGrid">
                <div className="statBox"><span>SUPPORTING</span><strong>{supporting.length}</strong></div>
                <div className="statBox"><span>CONTRADICTING</span><strong>{contradicting.length}</strong></div>
                <div className="statBox"><span>CONTEXTUAL</span><strong>{contextual.length}</strong></div>
                <div className="statBox"><span>INDEPENDENT DOMAINS</span><strong>{domains}</strong></div>
              </div>
              {result.evidence_analysis && (
                <div className="infoNote">
                  <span className="infoBadge">i</span>
                  <div>
                    <strong>Corroboration</strong>
                    <p>
                      {result.evidence_analysis.supporting_domains?.length || supporting.length} supporting ·{" "}
                      {result.evidence_analysis.contradicting_domains?.length || contradicting.length} contradicting
                    </p>
                  </div>
                </div>
              )}
              {result.methodology?.length > 0 && (
                <>
                  <h4 className="subHeading">Methodology</h4>
                  <ul className="cleanList">
                    {result.methodology.map((m, i) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </section>
      )}

      <footer className="footer">
        FACTYGO · Evidence-first AI investigation · Evidence over assumption
      </footer>
    </main>
  );
}
