"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const CLAIM_PROMPTS = [
  { text: "Everyday moon is orange", tag: "Science" },
  { text: "India is less populated country", tag: "Fact Check" },
  { text: "Lemon juice reduces diabetes", tag: "Health" },
  { text: "Solar panels generate zero electricity on cloudy days", tag: "Energy" },
  { text: "India's Chandrayaan-3 landed near the lunar south pole in 2023, which was 3 years ago", tag: "Multi-Claim + Math" },
  { text: "The Great Wall of China is visible from the Moon with the naked eye", tag: "Astronomy" },
  { text: "Does intermittent fasting improve insulin sensitivity?", tag: "Medical" },
  { text: "Antibiotics are effective against viral infections like the common cold", tag: "Health" },
];

const AUDIT_PROMPTS = [
  {
    text: "According to a 2023 landmark study (DOI: 10.1038/s41586-023-99999-z, PMID: 99999999), drinking 5 liters of lemon water cures Type 2 diabetes in 48 hours.",
    tag: "Hallucinated DOI & PMID",
  },
  {
    text: "The seminal Attention Is All You Need paper (arXiv:1706.03762) introduced the Transformer architecture in 2017.",
    tag: "Valid arXiv Citation",
  },
];

const LOADING_STEPS = [
  "Decomposing sub-claims & framing adversarial search queries…",
  "Auditing DOIs/PMIDs & searching PubMed, Wikipedia, and news…",
  "Deep-reading top articles & grading Evidence Pyramid tiers…",
  "Running symbolic math/unit checks & synthesizing report…",
];

function label(value) {
  return String(value || "").replaceAll("_", " ").toUpperCase();
}

function verdictTone(value) {
  const x = String(value || "").toUpperCase();
  if (x === "TRUE" || x === "VERIFIED") return "good";
  if (x === "FALSE" || x === "HALLUCINATED" || x === "BROKEN_LINK") return "bad";
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
          const excerpt = ev?.excerpt ? ` — “${ev.excerpt.slice(0, 140)}...”` : "";
          if (!url) {
            return (
              <sup key={eid} className="citationPill" title={`${title}${excerpt}`}>
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
                title={`${eid}: ${title}${domain ? ` (${domain})` : ""}${excerpt}`}
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

function AdaptiveVisualBlock({ block, evidenceById, sources }) {
  if (!block || !block.type) return null;

  if (block.type === "table" && Array.isArray(block.headers) && Array.isArray(block.rows)) {
    return (
      <div className="visualCard">
        <div className="visualHeader">
          <span className="visualBadge">STRUCTURED COMPARISON</span>
          <h4>{block.title || "Evidence Comparison"}</h4>
        </div>
        <div className="tableWrap">
          <table className="visualTable">
            <thead>
              <tr>
                {block.headers.map((h, i) => (
                  <th key={i}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {row.map((cell, cIdx) => (
                    <td key={cIdx}>{renderWithCitations(cell, evidenceById, sources)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (block.type === "timeline" && Array.isArray(block.events)) {
    return (
      <div className="visualCard">
        <div className="visualHeader">
          <span className="visualBadge">CHRONOLOGICAL TIMELINE</span>
          <h4>{block.title || "Verified Timeline"}</h4>
        </div>
        <div className="timelineList">
          {block.events.map((ev, idx) => (
            <div key={idx} className="timelineRow">
              <span className="timelineDate">{ev.date}</span>
              <span className="timelineDot" />
              <div className="timelineBody">
                <span>{ev.label}</span>
                {ev.evidence_id && renderWithCitations(`(${ev.evidence_id})`, evidenceById, sources)}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (block.type === "bar_chart" && Array.isArray(block.bars)) {
    const maxVal = Math.max(...block.bars.map(b => Number(b.value) || 0), 1);
    return (
      <div className="visualCard">
        <div className="visualHeader">
          <span className="visualBadge">QUANTITATIVE DATA</span>
          <h4>{block.title || "Quantitative Breakdown"}</h4>
        </div>
        <div className="barChartList">
          {block.bars.map((bar, idx) => {
            const pct = Math.min(100, Math.max(4, ((Number(bar.value) || 0) / maxVal) * 100));
            return (
              <div key={idx} className="barChartRow">
                <div className="barChartTop">
                  <span className="barChartLabel">
                    {bar.label} {bar.evidence_id && renderWithCitations(`(${bar.evidence_id})`, evidenceById, sources)}
                  </span>
                  <strong className="barChartVal">{bar.display || `${bar.value}${block.unit || ""}`}</strong>
                </div>
                <div className="barChartTrack">
                  <div className="barChartFill" style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return null;
}

export default function Home() {
  const [text, setText] = useState("");
  const [mode, setMode] = useState("auto"); // "auto" | "audit_ai"
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [copied, setCopied] = useState(false);
  const [showAllSources, setShowAllSources] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [shuffledPrompts, setShuffledPrompts] = useState(CLAIM_PROMPTS);
  const searchBoxRef = useRef(null);

  const activePromptBank = mode === "audit_ai" ? AUDIT_PROMPTS : CLAIM_PROMPTS;

  function shuffleSuggestions(bank = activePromptBank) {
    const copy = [...bank];
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    setShuffledPrompts(copy);
  }

  useEffect(() => {
    shuffleSuggestions(mode === "audit_ai" ? AUDIT_PROMPTS : CLAIM_PROMPTS);
  }, [mode]);

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
    return matches.length >= 2
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
    setShowAllSources(false);

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 45000);
      let response;
      try {
        response = await fetch(API + "/api/investigate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: claim, mode }),
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
  const citationAudits = result?.citation_audits || [];
  const keyTakeaways = result?.key_takeaways || [];
  const caveat = result?.caveat || "";
  const visualBlocks = result?.visual_blocks || [];

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
          studyTier: e.study_tier || "",
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
        studyTier: "",
        fullArticleRead: false,
        score: s.source_score ?? 0.65,
      };
    });
  }, [evidence, sources]);

  const visibleItems = showAllSources ? unifiedItems : unifiedItems.slice(0, 3);

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
  const noResults = result && !result.error && !unifiedItems.length && !citationAudits.length;

  async function copyMarkdownReport() {
    if (!result) return;
    const lines = [
      `# Factygo Investigation Report`,
      `**Claim:** ${result.claim || text}`,
      `**Verdict:** ${label(result.verdict)} (${confidence}% confidence)`,
      `**Summary:** ${result.explanation}`,
      ...(keyTakeaways.length ? [``, `## Key Takeaways`, ...keyTakeaways.map(t => `- ${t}`)] : []),
      ...(caveat ? [``, `> **Caveat:** ${caveat}`] : []),
      ...(citationAudits.length ? [``, `## Citation Audit`, ...citationAudits.map(c => `- **${c.identifier}**: ${c.status} — ${c.detail}`)] : []),
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
        <span className="topTag">EVIDENCE-FIRST VERIFICATION & AI AUDITOR</span>
      </div>

      <header className="hero">
        <div className="eyebrow">AI RESEARCH & AUDIT WORKSPACE</div>
        <h1>Investigate claims.<br /><span>Audit AI outputs.</span></h1>
        <p>Verify claims against live primary sources, check symbolic math & timelines, or catch hallucinated DOIs and links in AI-generated text.</p>
      </header>

      <section className="searchCard" ref={searchBoxRef}>
        <div className="searchLabelRow">
          <div className="modePills" role="tablist" aria-label="Investigation mode">
            <button
              type="button"
              className={"modePill" + (mode === "auto" ? " active" : "")}
              onClick={() => setMode("auto")}
            >
              Verify Claim
            </button>
            <button
              type="button"
              className={"modePill" + (mode === "audit_ai" ? " active" : "")}
              onClick={() => setMode("audit_ai")}
            >
              Audit AI Text & Citations
            </button>
          </div>
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
            placeholder={
              mode === "audit_ai"
                ? "Paste a ChatGPT/Gemini paragraph with DOIs, PMIDs, arXiv IDs, or URLs to audit..."
                : "Write your claim or question..."
            }
            rows={2}
            disabled={loading}
          />
          {showSuggestions && !loading && (
            <div className="suggestionsDropdown" role="listbox" aria-label="Suggested claims and questions">
              <div className="suggestionsHeader">
                <span>{mode === "audit_ai" ? "SAMPLE AI CITATION AUDITS" : "SUGGESTED CLAIMS & QUESTIONS"}</span>
                <span>CLICK TO FILL</span>
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
          <span className="hint">Ctrl/Cmd + Enter to run · Auto-detects DOIs, PMIDs, arXiv & URLs</span>
          <button className="primaryButton" onClick={() => investigate()} disabled={loading || !text.trim()}>
            {loading ? <><span className="spinner" /> Investigating…</> : <>{mode === "audit_ai" ? "Audit Citations" : "Investigate"} <span>→</span></>}
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
          {/* 1. Micro-Report Hero & Temporal/Domain Strip */}
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

              {keyTakeaways.length > 0 && (
                <ul className="takeawayList">
                  {keyTakeaways.map((item, idx) => (
                    <li key={idx}>{renderWithCitations(item, evidenceById, sources)}</li>
                  ))}
                </ul>
              )}

              {caveat && (
                <div className="caveatBanner">
                  <strong>Caveat:</strong> {renderWithCitations(caveat, evidenceById, sources)}
                </div>
              )}

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
                {result.claim_analysis?.valid_as_of && (
                  <span className="metaPill">Valid As Of: {result.claim_analysis.valid_as_of}</span>
                )}
                {result.claim_analysis?.volatility && (
                  <span className="metaPill">{result.claim_analysis.volatility}</span>
                )}
                <span className="metaPill">
                  Mode: {result.claim_analysis?.knowledge_mode === "hybrid_encyclopedic" ? "HYBRID SCIENCE" : "STRICT EVIDENCE"}
                </span>
                <span className="metaPill">{domains} Independent {domains === 1 ? "Domain" : "Domains"}</span>
              </div>

              {ratio.total > 0 && (
                <div className="ratioWrap compactRatio">
                  <div className="ratioLegend">
                    <span>Evidence Consensus (Adversarial Support vs. Counter-Evidence)</span>
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

          {/* 2. Citation & DOI Hallucination Audit Section (when DOIs/PMIDs/arXiv/URLs are present) */}
          {citationAudits.length > 0 && (
            <div className="visualSection">
              <div className="visualCard">
                <div className="visualHeader">
                  <span className="visualBadge">REGISTRY & CITATION HALLUCINATION AUDIT</span>
                  <h4>Cited Identifiers Checked ({citationAudits.length})</h4>
                </div>
                <div className="auditList">
                  {citationAudits.map((aud, idx) => (
                    <div key={idx} className="auditRow">
                      <span className={"subClaimBadge " + verdictTone(aud.status)}>{aud.status}</span>
                      <div className="auditBody">
                        <strong>{aud.identifier}</strong> — <span>{aud.title}</span>
                        <p>{aud.detail}</p>
                      </div>
                      {aud.url && (
                        <a href={aud.url} target="_blank" rel="noreferrer" className="citationPill">
                          Verify ↗
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 3. Adaptive Visual Blocks (Tables, Timelines, Bar Charts) */}
          {visualBlocks.length > 0 && (
            <div className="visualSection">
              {visualBlocks.map((blk, idx) => (
                <AdaptiveVisualBlock key={idx} block={blk} evidenceById={evidenceById} sources={sources} />
              ))}
            </div>
          )}

          {/* 4. Progressive-Disclosure Clickable Web Sources & Evidence Pyramid */}
          <div className="unifiedBody">
            <div className="sectionHeaderRow">
              <div>
                <span className="sectionKicker">VERIFIED WEB SOURCES & EVIDENCE PYRAMID</span>
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
              <>
                <div className="cardStack">
                  {visibleItems.map((item) => {
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
                            {item.studyTier && <span className="studyTierPill">{item.studyTier}</span>}
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

                {unifiedItems.length > 3 && (
                  <button
                    type="button"
                    className="showMoreSourcesBtn"
                    onClick={() => setShowAllSources(prev => !prev)}
                  >
                    {showAllSources
                      ? "Show fewer sources ▲"
                      : `Show all ${unifiedItems.length} sources (+${unifiedItems.length - 3} more) ▼`}
                  </button>
                )}
              </>
            )}

            {/* 5. Collapsible Research Queries, Symbolic Logic & Methodology Drawer */}
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
                    <strong>Deterministic Symbolic, Unit & Temporal Checks</strong>
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
        FACTYGO · Evidence-first AI verification & citation auditor · Evidence over assumption
      </footer>
    </main>
  );
}
