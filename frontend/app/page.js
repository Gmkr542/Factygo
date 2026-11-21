"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SAMPLE_PROMPTS = [
  { text: "Everyday moon is orange", tag: "Science" },
  { text: "India is less populated country", tag: "Fact Check" },
  { text: "Lemon juice reduces diabetes", tag: "Health" },
  { text: "Solar panels generate zero electricity on cloudy days", tag: "Energy" },
  { text: "India's Chandrayaan-3 landed near the lunar south pole in 2023, which was 3 years ago", tag: "Multi-Claim + Math" },
  { text: "The Great Wall of China is visible from the Moon with the naked eye", tag: "Astronomy" },
  { text: "Does intermittent fasting improve insulin sensitivity?", tag: "Medical" },
  { text: "Antibiotics are effective against viral infections like the common cold", tag: "Health" },
];

const LOADING_STEPS = [
  "Decomposing sub-claims & routing knowledge mode…",
  "Searching PubMed, Wikipedia, news, and authoritative sources…",
  "Deep-reading top articles & running symbolic math/date checks…",
  "Synthesizing grounded verdict with citations…",
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

function extractDomain(url, fallback = "") {
  if (fallback && fallback.includes(".")) return fallback.replace(/^www\./, "");
  if (!url) return fallback || "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return fallback || "";
  }
}

function renderWithCitations(text, evidenceById, sources) {
  const str = String(text || "");
  if (!str) return null;
  const parts = str.split(/(\(\s*E\d{1,2}(?:\s*,\s*E\d{1,2})*\s*\)|\[\s*E\d{1,2}(?:\s*,\s*E\d{1,2})*\s*\])/g);
  return parts.map((part, idx) => {
    const match = part.match(/^[\(\[]\s*(E\d{1,2}(?:\s*,\s*E\d{1,2})*)\s*[\)\]]$/);
    if (!match) return <span key={idx}>{part}</span>;
    const ids = match[1].split(",").map(s => s.trim());
    return (
      <span key={idx} className="citationCluster">
        {ids.map(eid => {
          const ev = evidenceById[eid];
          const numIdx = parseInt(eid.replace(/\D/g, ""), 10) - 1;
          const fallbackSrc = !ev && numIdx >= 0 && sources[numIdx] ? sources[numIdx] : null;
          const url = ev?.source_url || fallbackSrc?.url || "";
          const title = ev?.source_title || fallbackSrc?.title || eid;
          const domain = extractDomain(url, ev?.domain || fallbackSrc?.domain || "");
          if (!url) {
            return (
              <sup key={eid} className="citationPill" title={title}>
                {eid}
              </sup>
            );
          }
          return (
            <sup key={eid}>
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="citationPill"
                title={`${eid}: ${title}${domain ? ` (${domain})` : ""}`}
              >
                {eid}
              </a>
            </sup>
          );
        })}
      </span>
    );
  });
}

export default function Home() {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [copied, setCopied] = useState(false);
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

  useEffect(() => {
    if (!loading) {
      setLoadingStep(0);
      return;
    }
    const interval = setInterval(() => {
      setLoadingStep(prev => (prev < LOADING_STEPS.length - 1 ? prev + 1 : prev));
    }, 2400);
    return () => clearInterval(interval);
  }, [loading]);

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
    setCopied(false);

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
  const claimVerdicts = result?.claim_verdicts || [];
  const computedFacts = result?.computed_facts || [];

  const evidenceById = useMemo(() => {
    const map = {};
    evidence.forEach((e, idx) => {
      const eid = e.evidence_id || `E${String(idx + 1).padStart(2, "0")}`;
      map[eid] = e;
    });
    return map;
  }, [evidence]);

  const unifiedItems = useMemo(() => {
    if (evidence.length) {
      return evidence.map((e, idx) => {
        const eid = e.evidence_id || `E${String(idx + 1).padStart(2, "0")}`;
        const url = e.source_url || "";
        const matchedSource = sources.find(s => s.url === url) || {};
        const domain = extractDomain(url, e.domain || matchedSource.domain || "");
        return {
          id: eid,
          title: e.source_title || matchedSource.title || url || "Web Source",
          url,
          domain,
          publisher: e.publisher || matchedSource.publisher || domain || "Web Source",
          excerpt: e.excerpt || "",
          reason: e.reason || "",
          stance: String(e.stance || "contextual").toLowerCase(),
          sourceType: e.source_type || matchedSource.source_type || "Web Source",
          fullArticleRead: Boolean(e.full_article_read),
          score: e.source_score ?? matchedSource.source_score ?? 0.65,
        };
      });
    }
    return sources.map((s, idx) => {
      const eid = `E${String(idx + 1).padStart(2, "0")}`;
      const domain = extractDomain(s.url, s.domain || "");
      return {
        id: eid,
        title: s.title || s.url || "Web Source",
        url: s.url || "",
        domain,
        publisher: s.publisher || domain || "Web Source",
        excerpt: "",
        reason: "",
        stance: "contextual",
        sourceType: s.source_type || "Web Source",
        fullArticleRead: false,
        score: s.source_score ?? 0.65,
      };
    });
  }, [evidence, sources]);

  const supporting = useMemo(
    () => unifiedItems.filter(e => e.stance === "supporting"),
    [unifiedItems]
  );
  const contradicting = useMemo(
    () => unifiedItems.filter(e => e.stance === "contradicting"),
    [unifiedItems]
  );
  const contextual = useMemo(
    () => unifiedItems.filter(e => e.stance === "contextual"),
    [unifiedItems]
  );

  const ratio = useMemo(() => {
    const total = supporting.length + contradicting.length + contextual.length;
    if (!total) return { sup: 0, con: 0, ctx: 0, total: 0 };
    return {
      sup: (supporting.length / total) * 100,
      con: (contradicting.length / total) * 100,
      ctx: (contextual.length / total) * 100,
      total,
    };
  }, [supporting.length, contradicting.length, contextual.length]);

  const domains = useMemo(() => {
    const hosts = new Set(unifiedItems.map(item => item.domain).filter(Boolean));
    if (hosts.size > 0) return hosts.size;
    return Number(result?.evidence_analysis?.independent_domains || 0);
  }, [result, unifiedItems]);

  const confidence = Number(result?.confidence || 0);
  const noResults = result && !result.error && !unifiedItems.length;

  async function copyMarkdownReport() {
    if (!result) return;
    const lines = [
      `# Factygo Investigation Report`,
      `**Claim:** ${result.claim || text}`,
      `**Verdict:** ${label(result.verdict)} (${confidence}% confidence)`,
      `**Summary:** ${result.explanation}`,
      `**Evidence:** ${supporting.length} supporting · ${contradicting.length} contradicting · ${contextual.length} contextual (${domains} independent domains)`,
      ``,
      `## Sources (${unifiedItems.length})`,
      ...unifiedItems.map((item, idx) => `${idx + 1}. [${item.title}](${item.url}) — ${item.publisher}`),
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch {
      setCopied(false);
    }
  }

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
        <section className="loadingCard shimmerCard" aria-live="polite">
          <div className="loadingIcon"><span className="spinner dark" /></div>
          <div className="loadingBody">
            <div className="loadingHeaderRow">
              <strong>Investigating claim</strong>
              <span className="stepPill">Step {loadingStep + 1} of {LOADING_STEPS.length}</span>
            </div>
            <p>{LOADING_STEPS[loadingStep]}</p>
            <div className="stepTrack" aria-hidden="true">
              {LOADING_STEPS.map((_, i) => (
                <span key={i} className={"stepDot" + (i <= loadingStep ? " active" : "")} />
              ))}
            </div>
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
          {/* 1. Unified Hero & Metadata Strip */}
          <div className="resultHero">
            <div className="verdictBlock">
              <div className="verdictTopRow">
                <div className={"verdictBadge " + verdictTone(result.verdict)}>
                  <span className="verdictDot" />
                  {label(result.verdict)}
                </div>
                <button
                  type="button"
                  className={"copyReportBtn" + (copied ? " copied" : "")}
                  onClick={copyMarkdownReport}
                  title="Copy formatted Markdown report"
                >
                  {copied ? "✓ Copied Report" : "⧉ Copy Report"}
                </button>
              </div>

              <h2 className="directResultHeadline">
                {renderWithCitations(result.explanation, evidenceById, sources)}
              </h2>

              {/* Multi-Claim Breakdown Chips when 2+ sub-claims exist */}
              {claimVerdicts.length > 1 && (
                <div className="subClaimList">
                  {claimVerdicts.map((cv, idx) => (
                    <div key={idx} className="subClaimRow">
                      <span className={"subClaimBadge " + verdictTone(cv.verdict)}>
                        {label(cv.verdict)}
                      </span>
                      <span className="subClaimText">{cv.subclaim}</span>
                      {cv.evidence_id && <span className="idBadge">{cv.evidence_id}</span>}
                    </div>
                  ))}
                </div>
              )}

              <div className="unifiedMetaStrip">
                <span className="metaPill">Scope: {label(result.claim_analysis?.jurisdiction || "GLOBAL")}</span>
                <span className="metaPill">Domain: {label(result.claim_analysis?.domain || "GENERAL")}</span>
                <span className="metaPill">
                  Mode: {result.claim_analysis?.knowledge_mode === "hybrid_encyclopedic" ? "HYBRID SCIENCE" : "STRICT EVIDENCE"}
                </span>
                <span className="metaPill">{domains} Independent {domains === 1 ? "Domain" : "Domains"}</span>
              </div>

              {ratio.total > 0 && (
                <div className="ratioWrap compactRatio">
                  <div className="ratioLegend">
                    <span>Evidence Consensus</span>
                    <span>
                      {supporting.length} supporting · {contradicting.length} contradicting · {contextual.length} context
                    </span>
                  </div>
                  <div className="ratioBar" role="img" aria-label="Evidence stance distribution">
                    {ratio.sup > 0 && (
                      <div className="ratioSeg sup" style={{ width: ratio.sup + "%" }} title={`Supporting: ${supporting.length}`} />
                    )}
                    {ratio.con > 0 && (
                      <div className="ratioSeg con" style={{ width: ratio.con + "%" }} title={`Contradicting: ${contradicting.length}`} />
                    )}
                    {ratio.ctx > 0 && (
                      <div className="ratioSeg ctx" style={{ width: ratio.ctx + "%" }} title={`Contextual: ${contextual.length}`} />
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className={"confidenceMeter " + confidenceTone(confidence)}>
              <div className="confidenceRing" style={{ "--confidence": confidence + "%" }}>
                <div className="confidenceInner">{confidence}%</div>
              </div>
              <span className="confidenceLabel">CONFIDENCE</span>
            </div>
          </div>

          {/* 2. Unified Clickable Web Sources & Evidence List */}
          <div className="unifiedBody">
            <div className="sectionHeaderRow">
              <div>
                <span className="sectionKicker">VERIFIED WEB SOURCES & EVIDENCE</span>
                <h3>Web Sources ({unifiedItems.length})</h3>
              </div>
              <span className="clickHint">Click any card to open original source ↗</span>
            </div>

            {noResults ? (
              <div className="emptyBox">
                <div className="emptyIcon">?</div>
                <strong>No sufficiently relevant evidence</strong>
                <p>Factygo could not retrieve enough reliable web evidence to determine whether this claim is true or false.</p>
                <button className="secondaryButton" onClick={() => investigate()}>Search again</button>
              </div>
            ) : (
              <div className="cardStack">
                {unifiedItems.map((item) => {
                  const faviconUrl = item.domain && item.domain.includes(".")
                    ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(item.domain)}&sz=32`
                    : "";
                  const CardTag = item.url ? "a" : "div";
                  const linkProps = item.url
                    ? { href: item.url, target: "_blank", rel: "noreferrer" }
                    : {};
                  return (
                    <CardTag key={item.id} className="unifiedSourceCard" {...linkProps}>
                      <div className="unifiedCardHeader">
                        <div className="sourceIdentity">
                          {faviconUrl ? (
                            <img
                              src={faviconUrl}
                              alt=""
                              width={18}
                              height={18}
                              className="sourceFavicon"
                              loading="lazy"
                            />
                          ) : (
                            <span className="sourceFaviconFallback">🌐</span>
                          )}
                          <div className="sourceTitleBlock">
                            <span className="unifiedCardTitle">
                              {item.title} {item.url && <span className="extArrow">↗</span>}
                            </span>
                            <span className="unifiedCardPublisher">
                              {item.publisher}{item.domain && item.publisher.toLowerCase() !== item.domain.toLowerCase() ? ` · ${item.domain}` : ""}
                            </span>
                          </div>
                        </div>

                        <div className="pillGroup">
                          <span className="idBadge">{item.id}</span>
                          <span className={"stance " + item.stance}>{label(item.stance)}</span>
                          {item.fullArticleRead && <span className="deepReadPill">Full Article</span>}
                          <span className="authorityPill">{item.sourceType}</span>
                          <span className="metaPill">{Math.round(Number(item.score) * 100)}/100</span>
                        </div>
                      </div>

                      {item.excerpt && (
                        <p className="unifiedExcerpt">“{item.excerpt}”</p>
                      )}
                      {item.reason && (
                        <p className="unifiedReason">{item.reason}</p>
                      )}
                    </CardTag>
                  );
                })}
              </div>
            )}

            {/* 3. Collapsible Research Queries, Symbolic Logic & Methodology Drawer */}
            <details className="researchDrawer">
              <summary>
                <span>Research queries, symbolic logic & methodology ({(result.research_questions || []).length} queries)</span>
                <span className="drawerChevron">▾</span>
              </summary>
              <div className="drawerContent">
                <div className="drawerClaimBox">
                  <strong>Investigated Input:</strong> {result.claim || text}
                </div>

                {computedFacts.length > 0 && (
                  <div className="drawerLogicBox">
                    <strong>Deterministic Symbolic & Temporal Checks</strong>
                    <ul>
                      {computedFacts.map((fact, idx) => (
                        <li key={idx}>{fact}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {(result.research_questions || []).map((q) => (
                  <div className="drawerQuestionItem" key={q.id}>
                    <div className="drawerQHeader">
                      <span className="qBadge">Q{q.id}</span>
                      <strong>{q.question}</strong>
                    </div>
                    <p>{q.raw_answer}</p>
                  </div>
                ))}

                {result.methodology?.length > 0 && (
                  <div className="drawerMethodology">
                    <strong>Verification Pipeline</strong>
                    <ul>
                      {result.methodology.map((m, i) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </details>
          </div>
        </section>
      )}

      <footer className="footer">
        FACTYGO · Evidence-first AI investigation · Evidence over assumption
      </footer>
    </main>
  );
}
