/* crux · Cases list + detail screen components
   Includes Stage-2 research-loop automation with per-plan states:
   idle → running (spinner) → done (SourceChips) | empty | error (retry).
*/

const STAGE_NAMES = ["Sharpen", "Bake-off", "Gather", "Weigh", "Probe"];
const STAGE_COLORS = [
  "var(--st-1)",
  "var(--st-2)",
  "var(--st-3)",
  "var(--st-4)",
  "var(--st-5)",
];

const STATES = {
  IDLE: "idle",
  COPIED: "copied",
  LOADING: "loading",
  ERROR: "error",
};

function Pill({ state }) {
  const labels = {
    confirmed: "confirmed",
    killed: "killed",
    inconclusive: "inconclusive",
    awaiting: "awaiting",
    progress: "in progress",
  };
  return (
    <span className={`pill ${state || "awaiting"}`}>
      {labels[state] || state}
    </span>
  );
}

function BakeOffStrip({ plans }) {
  if (!plans || plans.length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {plans.map((p) => {
        const won = p.state === "won";
        const lead = p.state === "leading" || won || p.current_rank === 1;
        const ruledOut =
          p.state === "ruled-out" || p.rankStanding === "ruled-out";
        const ruledIn = p.rankStanding === "ruled-in";
        const pct = Math.round((p.standing || 0) * 100);
        return (
          <div
            key={p.key}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              opacity: ruledOut ? 0.5 : 1,
            }}
          >
            <span
              className="mono"
              style={{
                fontSize: "var(--text-sm)",
                fontWeight: 700,
                color: lead ? "var(--crux)" : "var(--text-muted)",
                width: 16,
                flex: "none",
              }}
            >
              {p.key}
            </span>
            <div
              style={{
                flex: 1,
                height: 22,
                background: "var(--surface-2)",
                borderRadius: "var(--radius-sm)",
                overflow: "hidden",
                position: "relative",
              }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: "100%",
                  background: lead ? "var(--crux)" : "var(--st-2)",
                  borderRadius: "var(--radius-sm)",
                  transition: "width var(--speed)",
                }}
              ></div>
              <span
                style={{
                  position: "absolute",
                  left: 10,
                  top: 0,
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  fontSize: "var(--text-sm)",
                  fontWeight: 600,
                  color: pct > 22 && lead ? "#fff" : "var(--text)",
                  textDecoration: ruledOut ? "line-through" : "none",
                }}
              >
                {p.name}
              </span>
            </div>
            {ruledIn && (
              <span
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  width: 52,
                  textAlign: "right",
                  flex: "none",
                  color: "var(--green)",
                }}
              >
                ✓ FIT
              </span>
            )}
            {!ruledIn && (
              <span
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  width: 52,
                  textAlign: "right",
                  flex: "none",
                  color: won ? "var(--green)" : "var(--text-sub)",
                }}
              >
                {won ? "✓ WON" : `${pct}%`}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function CaseCard({ id, title, stage, verdict, plans, onClick }) {
  const [hovered, setHovered] = React.useState(false);
  const closed =
    verdict === "confirmed" ||
    verdict === "killed" ||
    verdict === "inconclusive";

  const spineColor =
    verdict === "confirmed"
      ? "var(--green)"
      : verdict === "killed"
        ? "var(--red)"
        : verdict === "inconclusive"
          ? "var(--amber)"
          : "var(--crux)";
  const spineBg =
    verdict === "confirmed"
      ? "var(--green-bg)"
      : verdict === "killed"
        ? "var(--red-bg)"
        : verdict === "inconclusive"
          ? "var(--amber-bg)"
          : "var(--surface-2)";

  const safeStage = Math.max(0, Math.min(stage || 0, 4));
  const stagePips = STAGE_NAMES.map((_, i) => {
    const done = closed || i < safeStage;
    const now = !closed && i === safeStage;
    const bg = done ? STAGE_COLORS[i] : now ? STAGE_COLORS[i] : "var(--border)";
    return (
      <div
        key={i}
        style={{ flex: 1, height: 5, borderRadius: 3, background: bg }}
      ></div>
    );
  });

  const stageLabel = closed ? "CLOSED" : `STAGE ${safeStage + 1}`;
  const stageName = STAGE_NAMES[Math.min(safeStage, 4)];

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        background: "var(--surface)",
        border: `1px solid ${hovered ? "var(--crux)" : "var(--border)"}`,
        borderRadius: "var(--radius)",
        overflow: "hidden",
        cursor: onClick ? "pointer" : "default",
        boxShadow: hovered ? "var(--shadow-hover)" : "var(--shadow-card)",
        transition: "box-shadow var(--speed), border-color var(--speed)",
      }}
    >
      <div
        style={{
          width: 118,
          flex: "none",
          background: spineBg,
          borderRight: "1px solid var(--border)",
          padding: "var(--space-3)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}
      >
        <div
          className="mono"
          style={{
            fontSize: "var(--text-2xs)",
            fontWeight: 700,
            color: closed ? spineColor : "var(--crux)",
          }}
        >
          {stageLabel}
        </div>
        <div
          className="mono"
          style={{
            fontSize: "var(--text-xs)",
            fontWeight: 700,
            color: "var(--text)",
            margin: "6px 0 10px",
          }}
        >
          {stageName}
        </div>
        <div style={{ display: "flex", gap: 4 }}>{stagePips}</div>
        <div
          className="mono"
          style={{
            fontSize: "var(--text-2xs)",
            color: "var(--text-sub)",
            marginTop: 10,
          }}
        >
          {id && id.length > 12 ? id.substring(0, 8).toUpperCase() : id}
        </div>
      </div>

      <div style={{ flex: 1, minWidth: 0, padding: "var(--space-4)" }}>
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "var(--space-3)",
            marginBottom: "var(--space-3)",
          }}
        >
          <h3
            style={{
              fontSize: "var(--text-lg)",
              fontWeight: 600,
              color: "var(--text)",
              lineHeight: 1.35,
              textWrap: "pretty",
            }}
          >
            {title}
          </h3>
          <Pill state={verdict} />
        </div>
        <BakeOffStrip plans={plans} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NewCaseModal
// ---------------------------------------------------------------------------

function NewCaseModal({ onClose, onCaseCreated }) {
  const [step, setStep] = React.useState("input");
  const [raw, setRaw] = React.useState("");
  const [sharpened, setSharpened] = React.useState("");
  const [notInvestigating, setNotInvestigating] = React.useState([]);
  const [error, setError] = React.useState("");
  const [priorLearnings, setPriorLearnings] = React.useState([]);

  React.useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function handleSharpen() {
    if (!raw.trim()) return;
    setStep("loading");
    setError("");
    setPriorLearnings([]);
    try {
      const resp = await fetch("/api/cases/sharpen", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ raw_problem: raw }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `API error ${resp.status}`);
      }
      const data = await resp.json();
      setSharpened(data.sharpened);
      setNotInvestigating(data.not_investigating || []);
      // Fetch prior learnings silently; failures do not block the flow
      try {
        const relResp = await fetch("/api/cases/related-text", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ sharpened: data.sharpened, mechanisms: [] }),
        });
        if (relResp.ok) {
          const relData = await relResp.json();
          setPriorLearnings(relData.matches || []);
        }
      } catch (_) {
        // silent failure — prior learnings are advisory only
      }
      setStep("confirm");
    } catch (err) {
      setError(err.message || "Sharpen failed. Please try again.");
      setStep("input");
    }
  }

  async function handleCreate() {
    setStep("creating");
    setError("");
    try {
      const resp = await fetch("/api/cases", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          raw_problem: raw,
          sharpened,
          not_investigating: notInvestigating,
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Create failed ${resp.status}`);
      }
      const data = await resp.json();
      onClose();
      if (onCaseCreated) onCaseCreated(data.id);
    } catch (err) {
      setError(err.message || "Could not create case. Please try again.");
      setStep("confirm");
    }
  }

  const isLoading = step === "loading";
  const isCreating = step === "creating";

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="New case"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-5)",
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 560,
          maxWidth: "100%",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-card)",
          padding: "var(--space-6)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--space-4)",
          }}
        >
          <h2
            style={{
              fontSize: "var(--text-xl)",
              fontWeight: 800,
              color: "var(--text)",
            }}
          >
            New case
          </h2>
          <button
            className="btn btn-sm"
            onClick={onClose}
            aria-label="Close"
            style={{ padding: "6px 8px" }}
          >
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>

        {(step === "input" || step === "loading") && (
          <div>
            <label
              style={{
                display: "block",
                fontSize: "var(--text-sm)",
                fontWeight: 600,
                color: "var(--text-muted)",
                marginBottom: "var(--space-2)",
              }}
            >
              Paste the messy problem
            </label>
            <textarea
              value={raw}
              onChange={(e) => {
                setRaw(e.target.value);
                setError("");
              }}
              placeholder="Dump everything you know — symptoms, timeline, what you've tried…"
              rows={6}
              disabled={isLoading}
              style={{
                width: "100%",
                resize: "vertical",
                padding: "var(--space-3)",
                fontSize: "var(--text-base)",
                color: "var(--text)",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                lineHeight: 1.55,
                boxSizing: "border-box",
                opacity: isLoading ? 0.6 : 1,
              }}
            />
            {error && (
              <p
                role="alert"
                style={{
                  color: "var(--red)",
                  fontSize: "var(--text-sm)",
                  marginTop: "var(--space-2)",
                }}
              >
                {error}
              </p>
            )}
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "var(--space-2)",
                marginTop: "var(--space-5)",
              }}
            >
              <button className="btn" onClick={onClose} disabled={isLoading}>
                Cancel
              </button>
              <button
                className="btn btn-crux"
                onClick={handleSharpen}
                disabled={!raw.trim() || isLoading}
                aria-busy={isLoading}
              >
                {isLoading ? (
                  <>
                    <i
                      className="ti ti-loader-2 crux-spin"
                      aria-hidden="true"
                    ></i>{" "}
                    Sharpening…
                  </>
                ) : (
                  <>
                    <i className="ti ti-arrow-right" aria-hidden="true"></i>{" "}
                    Sharpen
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {(step === "confirm" || step === "creating") && (
          <div>
            <div
              className="mono"
              style={{
                fontSize: "var(--text-2xs)",
                fontWeight: 700,
                color: "var(--crux)",
                marginBottom: "var(--space-2)",
              }}
            >
              SHARPENED STATEMENT
            </div>
            <div
              style={{
                background: "var(--crux-tint)",
                border: "1px solid var(--crux)",
                borderRadius: "var(--radius)",
                padding: "var(--space-4)",
                fontSize: "var(--text-lg)",
                color: "var(--text)",
                lineHeight: 1.5,
                marginBottom: "var(--space-4)",
              }}
            >
              {sharpened}
            </div>
            {notInvestigating.length > 0 && (
              <div style={{ marginBottom: "var(--space-4)" }}>
                <div
                  className="mono"
                  style={{
                    fontSize: "var(--text-2xs)",
                    fontWeight: 700,
                    color: "var(--text-sub)",
                    marginBottom: "var(--space-2)",
                  }}
                >
                  NOT INVESTIGATING
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "var(--space-2)",
                    flexWrap: "wrap",
                  }}
                >
                  {notInvestigating.map((item) => (
                    <span
                      key={item}
                      className="src"
                      style={{ textDecoration: "line-through" }}
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <PriorLearnings matches={priorLearnings} onNavigate={null} />

            {error && (
              <p
                role="alert"
                style={{
                  color: "var(--red)",
                  fontSize: "var(--text-sm)",
                  marginBottom: "var(--space-3)",
                }}
              >
                {error}
              </p>
            )}

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "var(--space-2)",
                marginTop: "var(--space-5)",
              }}
            >
              <button
                className="btn"
                onClick={() => setStep("input")}
                disabled={isCreating}
              >
                <i className="ti ti-arrow-left" aria-hidden="true"></i> Back
              </button>
              <button
                className="btn btn-crux"
                onClick={handleCreate}
                disabled={isCreating}
                aria-busy={isCreating}
              >
                {isCreating ? (
                  <>
                    <i
                      className="ti ti-loader-2 crux-spin"
                      aria-hidden="true"
                    ></i>{" "}
                    Creating…
                  </>
                ) : (
                  <>
                    <i className="ti ti-check" aria-hidden="true"></i> Create
                    case
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SourceChip — colour-coded by support_status; expandable with Verify actions
// ---------------------------------------------------------------------------

const _CHIP_COLORS = {
  supports:    { border: "var(--green)",  bg: "var(--green-bg)",  text: "var(--green)" },
  contradicts: { border: "var(--red)",    bg: "var(--red-bg)",    text: "var(--red)" },
  neutral:     { border: "var(--amber)",  bg: "var(--amber-bg)",  text: "var(--amber)" },
  inconclusive:{ border: "var(--amber)",  bg: "var(--amber-bg)",  text: "var(--amber)" },
};
const _CHIP_UNVERIFIED = { border: "var(--border)", bg: "var(--surface-2)", text: "var(--text-muted)" };

const _STATUS_LABEL = {
  supports:    "Supports",
  contradicts: "Contradicts",
  neutral:     "Partial",
  inconclusive:"Partial",
};

function SourceChip({
  id,
  kind,
  title,
  url,
  claim,
  support_status: initialStatus,
  rationale: initialRationale,
  manually_overridden: initialOverridden,
  onUpdate,
}) {
  const [expanded, setExpanded] = React.useState(false);
  const [currentStatus, setCurrentStatus] = React.useState(initialStatus || null);
  const [currentRationale, setCurrentRationale] = React.useState(initialRationale || "");
  const [currentOverridden, setCurrentOverridden] = React.useState(!!initialOverridden);
  const [verifying, setVerifying] = React.useState(false);
  const [verifyError, setVerifyError] = React.useState("");

  React.useEffect(() => {
    setCurrentStatus(initialStatus || null);
    setCurrentRationale(initialRationale || "");
    setCurrentOverridden(!!initialOverridden);
  }, [initialStatus, initialRationale, initialOverridden]);

  const iconMap = { book: "ti-book", article: "ti-article", youtube: "ti-brand-youtube" };
  const icon = iconMap[kind] || "ti-file";
  const colors = _CHIP_COLORS[currentStatus] || _CHIP_UNVERIFIED;
  const statusLabel = _STATUS_LABEL[currentStatus] || "Unverified";

  function _applyUpdate(data) {
    setCurrentStatus(data.support_status || null);
    setCurrentRationale(data.rationale || "");
    setCurrentOverridden(!!data.manually_overridden);
    if (onUpdate) onUpdate(data);
  }

  async function handleVerify() {
    if (!id) return;
    setVerifying(true);
    setVerifyError("");
    try {
      const resp = await fetch(`/api/sources/${id}/run-verify`, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || `Error ${resp.status}`);
      _applyUpdate(data);
    } catch (err) {
      setVerifyError(err.message || "Verification failed.");
    } finally {
      setVerifying(false);
    }
  }

  async function handleOverride(newStatus) {
    if (!id || !newStatus) return;
    const rat = currentRationale || "Manually set.";
    try {
      const resp = await fetch(`/api/sources/${id}/status-override`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ support_status: newStatus, rationale: rat }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) return;
      _applyUpdate(data);
    } catch (_) {}
  }

  async function handleAccept() {
    if (!id) return;
    try {
      const resp = await fetch(`/api/sources/${id}/accept-status`, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) return;
      _applyUpdate(data);
    } catch (_) {}
  }

  // Collapsed chip — button so it is keyboard-focusable by default
  if (!expanded) {
    return (
      <button
        className={`src ${kind}`}
        onClick={() => setExpanded(true)}
        aria-expanded={false}
        aria-label={`${title}: ${statusLabel}. Expand for details.`}
        style={{
          cursor: "pointer",
          border: `1px solid ${colors.border}`,
          background: colors.bg,
        }}
      >
        <i className={`ti ${icon}`} aria-hidden="true"></i>
        {title}
        <span
          className="mono"
          style={{ fontSize: "var(--text-2xs)", color: colors.text }}
          aria-label={`Status: ${statusLabel}`}
        >
          {statusLabel}
        </span>
        {currentOverridden && (
          <i
            className="ti ti-lock"
            aria-label="Manually overridden"
            title="Manually overridden"
            style={{ fontSize: 10, color: colors.text }}
          ></i>
        )}
      </button>
    );
  }

  // Expanded state — full-width panel (flex-basis:100% breaks out of chip row)
  return (
    <div
      style={{
        flexBasis: "100%",
        border: `1px solid ${colors.border}`,
        background: colors.bg,
        borderRadius: "var(--radius-sm)",
        padding: "var(--space-3)",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          marginBottom: "var(--space-2)",
          flexWrap: "wrap",
        }}
      >
        <button
          onClick={() => setExpanded(false)}
          aria-expanded={true}
          aria-label={`Collapse ${title}`}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 0,
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-sm)",
            color: "var(--text)",
          }}
        >
          <i className={`ti ${icon}`} aria-hidden="true"></i>
          {title}
          <i className="ti ti-chevron-up" aria-hidden="true" style={{ fontSize: 10 }}></i>
        </button>

        <span
          className="mono"
          style={{
            fontSize: "var(--text-2xs)",
            color: colors.text,
            fontWeight: 700,
          }}
        >
          {statusLabel}
        </span>

        {currentOverridden && (
          <span
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              color: colors.text,
              display: "inline-flex",
              alignItems: "center",
              gap: 3,
            }}
            aria-label="Manually overridden"
          >
            <i className="ti ti-lock" aria-hidden="true" style={{ fontSize: 10 }}></i>
            Overridden
          </span>
        )}

        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open source: ${title}`}
            style={{
              marginLeft: "auto",
              fontSize: "var(--text-2xs)",
              color: "var(--text-muted)",
            }}
          >
            <i className="ti ti-external-link" aria-hidden="true"></i>
          </a>
        )}
      </div>

      {/* Rationale */}
      <p
        style={{
          fontSize: "var(--text-sm)",
          color: "var(--text-muted)",
          lineHeight: 1.5,
          margin: "0 0 var(--space-2)",
        }}
      >
        {currentRationale ? (
          currentRationale
        ) : (
          <span style={{ fontStyle: "italic", color: "var(--text-sub)" }}>
            No rationale yet. Click Verify to analyse this source.
          </span>
        )}
      </p>

      {verifyError && (
        <p
          role="alert"
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--red)",
            margin: "0 0 var(--space-2)",
          }}
        >
          <i className="ti ti-alert-circle" aria-hidden="true"></i> {verifyError}
        </p>
      )}

      {/* Action row */}
      <div
        style={{
          display: "flex",
          gap: "var(--space-2)",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <button
          className="btn btn-sm"
          onClick={handleVerify}
          disabled={verifying}
          aria-label="Verify this source"
          style={{ fontSize: "var(--text-2xs)", padding: "3px 9px" }}
        >
          {verifying ? (
            <>
              <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>
              Verifying…
            </>
          ) : (
            <>
              <i className="ti ti-shield-check" aria-hidden="true"></i>
              Verify
            </>
          )}
        </button>

        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontSize: "var(--text-2xs)",
            color: "var(--text-muted)",
          }}
        >
          <span className="mono">Status:</span>
          <select
            value={currentStatus || ""}
            onChange={(e) => handleOverride(e.target.value)}
            aria-label="Override support status"
            style={{
              fontSize: "var(--text-2xs)",
              padding: "2px 4px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)",
              background: "var(--surface)",
              color: "var(--text)",
              cursor: "pointer",
            }}
          >
            <option value="">Unverified</option>
            <option value="supports">Supports</option>
            <option value="neutral">Partial</option>
            <option value="contradicts">Contradicts</option>
            <option value="inconclusive">Inconclusive</option>
          </select>
        </label>

        {currentOverridden && (
          <button
            className="btn btn-sm"
            onClick={handleAccept}
            aria-label="Accept AI-assigned status and clear override"
            style={{ fontSize: "var(--text-2xs)", padding: "3px 9px" }}
          >
            <i className="ti ti-check" aria-hidden="true"></i> Accept
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SourceForm — modal for manually adding a source (AC8 fallback)
// ---------------------------------------------------------------------------

function SourceForm({ planId, onClose, onAdded }) {
  const [kind, setKind] = React.useState("article");
  const [title, setTitle] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [claim, setClaim] = React.useState("");
  const [citation, setCitation] = React.useState("");
  const [errors, setErrors] = React.useState({});
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function validate() {
    const errs = {};
    if (!title.trim()) errs.title = "Title is required.";
    if (!claim.trim()) errs.claim = "Claim is required.";
    if (!citation.trim()) errs.citation = "Citation is required.";
    if (url.trim() && !/^https?:\/\/\S+$/.test(url.trim()))
      errs.url = "URL must start with http:// or https://.";
    return errs;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setSubmitting(true);
    setErrors({});
    try {
      const resp = await fetch("/api/sources", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          plan_id: planId,
          kind,
          title: title.trim(),
          url: url.trim() || null,
          claim: claim.trim(),
          citation: citation.trim(),
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${resp.status}`);
      }
      const data = await resp.json();
      onAdded(data);
      onClose();
    } catch (err) {
      setErrors({ submit: err.message || "Could not save source." });
    } finally {
      setSubmitting(false);
    }
  }

  const fieldStyle = {
    width: "100%",
    padding: "var(--space-2) var(--space-3)",
    fontSize: "var(--text-sm)",
    color: "var(--text)",
    background: "var(--surface-2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    boxSizing: "border-box",
  };
  const labelStyle = {
    display: "block",
    fontSize: "var(--text-2xs)",
    fontWeight: 700,
    color: "var(--text-muted)",
    marginBottom: "var(--space-1)",
    fontFamily: "var(--font-mono)",
    textTransform: "uppercase",
    letterSpacing: ".05em",
  };
  const errStyle = {
    color: "var(--red)",
    fontSize: "var(--text-2xs)",
    marginTop: 2,
  };

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Add source"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-5)",
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 480,
          maxWidth: "100%",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-card)",
          padding: "var(--space-6)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--space-4)",
          }}
        >
          <h2
            style={{
              fontSize: "var(--text-lg)",
              fontWeight: 800,
              color: "var(--text)",
            }}
          >
            Add source
          </h2>
          <button
            className="btn btn-sm"
            onClick={onClose}
            aria-label="Close"
            style={{ padding: "6px 8px" }}
          >
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>
        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: "var(--space-3)" }}>
            <label style={labelStyle}>Kind</label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              style={fieldStyle}
              disabled={submitting}
            >
              <option value="article">Article</option>
              <option value="book">Book</option>
              <option value="youtube">YouTube</option>
            </select>
          </div>
          <div style={{ marginBottom: "var(--space-3)" }}>
            <label style={labelStyle}>
              Title <span style={{ color: "var(--red)" }}>*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setErrors((p) => ({ ...p, title: "" }));
              }}
              style={{
                ...fieldStyle,
                borderColor: errors.title ? "var(--red)" : "var(--border)",
              }}
              disabled={submitting}
            />
            {errors.title && (
              <p role="alert" style={errStyle}>
                {errors.title}
              </p>
            )}
          </div>
          <div style={{ marginBottom: "var(--space-3)" }}>
            <label style={labelStyle}>
              URL <span style={{ color: "var(--text-sub)" }}>(optional)</span>
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setErrors((p) => ({ ...p, url: "" }));
              }}
              placeholder="https://…"
              style={{
                ...fieldStyle,
                borderColor: errors.url ? "var(--red)" : "var(--border)",
              }}
              disabled={submitting}
            />
            {errors.url && (
              <p role="alert" style={errStyle}>
                {errors.url}
              </p>
            )}
          </div>
          <div style={{ marginBottom: "var(--space-3)" }}>
            <label style={labelStyle}>
              Claim <span style={{ color: "var(--red)" }}>*</span>
            </label>
            <textarea
              rows={2}
              value={claim}
              onChange={(e) => {
                setClaim(e.target.value);
                setErrors((p) => ({ ...p, claim: "" }));
              }}
              placeholder="The assertion this source supports…"
              style={{
                ...fieldStyle,
                resize: "vertical",
                borderColor: errors.claim ? "var(--red)" : "var(--border)",
              }}
              disabled={submitting}
            />
            {errors.claim && (
              <p role="alert" style={errStyle}>
                {errors.claim}
              </p>
            )}
          </div>
          <div style={{ marginBottom: "var(--space-4)" }}>
            <label style={labelStyle}>
              Citation <span style={{ color: "var(--red)" }}>*</span>
            </label>
            <input
              type="text"
              value={citation}
              onChange={(e) => {
                setCitation(e.target.value);
                setErrors((p) => ({ ...p, citation: "" }));
              }}
              placeholder="Smith 2024 / APA string…"
              style={{
                ...fieldStyle,
                fontFamily: "var(--font-mono)",
                borderColor: errors.citation ? "var(--red)" : "var(--border)",
              }}
              disabled={submitting}
            />
            {errors.citation && (
              <p role="alert" style={errStyle}>
                {errors.citation}
              </p>
            )}
          </div>
          {errors.submit && (
            <p
              role="alert"
              style={{ ...errStyle, marginBottom: "var(--space-3)" }}
            >
              {errors.submit}
            </p>
          )}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: "var(--space-2)",
            }}
          >
            <button
              type="button"
              className="btn"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-crux"
              disabled={submitting}
              aria-busy={submitting}
            >
              {submitting ? (
                <>
                  <i
                    className="ti ti-loader-2 crux-spin"
                    aria-hidden="true"
                  ></i>{" "}
                  Saving…
                </>
              ) : (
                <>
                  <i className="ti ti-plus" aria-hidden="true"></i> Add source
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PriorLearnings — read-only section showing related confirmed/killed priors
// ---------------------------------------------------------------------------

const _PRIOR_PILL_STYLES = {
  confirmed: {
    label: "Confirmed Cause",
    color: "var(--green)",
    bg: "var(--green-bg)",
    border: "var(--green)",
  },
  killed: {
    label: "Killed Hypothesis",
    color: "var(--red)",
    bg: "var(--red-bg)",
    border: "var(--red)",
  },
  inconclusive: {
    label: "Inconclusive",
    color: "var(--amber)",
    bg: "var(--amber-bg)",
    border: "var(--amber)",
  },
};

function PriorLearnings({ matches, onNavigate }) {
  if (!matches || matches.length === 0) return null;

  return (
    <div style={{ marginBottom: "var(--space-5)" }}>
      <div
        className="mono"
        style={{
          fontSize: "var(--text-2xs)",
          fontWeight: 700,
          color: "var(--text-sub)",
          marginBottom: "var(--space-3)",
        }}
      >
        PRIOR LEARNINGS
      </div>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-2)",
        }}
      >
        {matches.map((m) => {
          const pill =
            _PRIOR_PILL_STYLES[m.verdict_outcome] ||
            _PRIOR_PILL_STYLES.inconclusive;
          return (
            <div
              key={m.case_id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "space-between",
                gap: "var(--space-3)",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "var(--space-3) var(--space-4)",
              }}
            >
              <span
                style={{
                  flex: 1,
                  fontSize: "var(--text-sm)",
                  color: "var(--text)",
                  lineHeight: 1.5,
                }}
              >
                {m.sharpened_snippet}
              </span>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  flex: "none",
                }}
              >
                <span
                  className="mono"
                  style={{
                    fontSize: "var(--text-2xs)",
                    fontWeight: 700,
                    color: pill.color,
                    background: pill.bg,
                    border: `1px solid ${pill.border}`,
                    borderRadius: "var(--radius-pill)",
                    padding: "2px 8px",
                    whiteSpace: "nowrap",
                  }}
                >
                  {pill.label}
                </span>
                <button
                  className="btn btn-sm"
                  onClick={() => onNavigate && onNavigate(m.case_id)}
                  aria-label={`View source case for: ${m.sharpened_snippet}`}
                  style={{ padding: "3px 9px", fontSize: "var(--text-2xs)" }}
                >
                  <i className="ti ti-arrow-right" aria-hidden="true"></i> View
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SuggestPanel — pick-to-attach UI for AI-ranked source candidates (issue #84)
// States: idle → loading → results | empty | error
// ---------------------------------------------------------------------------

function SuggestPanel({ planId, onAttached }) {
  const [state, setState] = React.useState("idle"); // idle | loading | results | empty | error
  const [candidates, setCandidates] = React.useState([]);
  const [selected, setSelected] = React.useState(new Set());
  const [addState, setAddState] = React.useState("idle"); // idle | loading | error
  const [addError, setAddError] = React.useState("");

  const iconMap = {
    book: "ti-book",
    article: "ti-article",
    youtube: "ti-brand-youtube",
  };

  async function handleSuggest() {
    setState("loading");
    setAddError("");
    try {
      const resp = await fetch(`/api/plans/${planId}/gather/suggest`, {
        method: "POST",
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setState("error");
        return;
      }
      const cands = data.candidates || [];
      setCandidates(cands);
      setSelected(new Set());
      setState(cands.length === 0 ? "empty" : "results");
    } catch {
      setState("error");
    }
  }

  function toggleOne(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === candidates.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(candidates.map((c) => c.candidate_id)));
    }
  }

  async function handleAddSelected() {
    const chosen = candidates.filter((c) => selected.has(c.candidate_id));
    if (chosen.length === 0) return;
    setAddState("loading");
    setAddError("");
    try {
      const resp = await fetch("/api/sources/batch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          plan_id: planId,
          sources: chosen.map((c) => ({
            kind: c.kind,
            title: c.title,
            url: c.url,
            claim: c.claim,
            citation: c.citation,
          })),
        }),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        setAddError(
          errData.detail || `Could not attach sources (${resp.status})`,
        );
        setAddState("error");
        return;
      }
      setAddState("idle");
      setCandidates([]);
      setSelected(new Set());
      setState("idle");
      if (onAttached) onAttached();
    } catch (err) {
      setAddError(err.message || "Network error. Please try again.");
      setAddState("error");
    }
  }

  const allSelected =
    candidates.length > 0 && selected.size === candidates.length;
  const noneSelected = selected.size === 0;
  const adding = addState === "loading";

  if (state === "idle") {
    return (
      <button
        className="btn btn-sm"
        onClick={handleSuggest}
        style={{ padding: "3px 9px", fontSize: "var(--text-2xs)" }}
        aria-label="Suggest sources for this plan"
      >
        <i className="ti ti-sparkles" aria-hidden="true"></i> Suggest sources
      </button>
    );
  }

  if (state === "loading") {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          color: "var(--text-muted)",
          fontSize: "var(--text-sm)",
          padding: "var(--space-2) 0",
        }}
      >
        <i
          className="ti ti-loader-2 crux-spin"
          aria-hidden="true"
          style={{ color: "var(--crux)" }}
        ></i>
        Suggesting sources…
      </div>
    );
  }

  if (state === "error") {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: "var(--text-sm)", color: "var(--red)" }}>
          <i className="ti ti-alert-circle" aria-hidden="true"></i> Suggest
          failed.
        </span>
        <button
          className="btn btn-sm"
          onClick={handleSuggest}
          style={{ fontSize: "var(--text-2xs)" }}
        >
          <i className="ti ti-refresh" aria-hidden="true"></i> Retry
        </button>
        <button
          className="btn btn-sm"
          onClick={() => setState("idle")}
          style={{ fontSize: "var(--text-2xs)" }}
        >
          Cancel
        </button>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-sub)" }}>
          No sources found — add one manually.
        </span>
        <button
          className="btn btn-sm"
          onClick={() => setState("idle")}
          style={{ fontSize: "var(--text-2xs)", padding: "2px 7px" }}
        >
          Dismiss
        </button>
      </div>
    );
  }

  // results state
  return (
    <div
      style={{
        marginTop: "var(--space-3)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        overflow: "hidden",
      }}
    >
      {/* Header bar: select-all + count + add button */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          padding: "var(--space-2) var(--space-3)",
          background: "var(--surface-2)",
          borderBottom: "1px solid var(--border)",
          flexWrap: "wrap",
        }}
      >
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
            cursor: "pointer",
            fontSize: "var(--text-sm)",
            color: "var(--text-muted)",
            userSelect: "none",
          }}
        >
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            aria-label="Select all candidates"
            style={{
              accentColor: "var(--crux)",
              width: 14,
              height: 14,
              cursor: "pointer",
            }}
          />
          Select all
        </label>
        <span
          className="mono"
          style={{
            fontSize: "var(--text-2xs)",
            color: "var(--text-sub)",
            flex: 1,
          }}
        >
          {selected.size} of {candidates.length} selected
        </span>
        <button
          className="btn btn-sm btn-crux"
          onClick={handleAddSelected}
          disabled={noneSelected || adding}
          aria-busy={adding}
          style={{
            fontSize: "var(--text-2xs)",
            padding: "3px 10px",
            opacity: noneSelected || adding ? 0.5 : 1,
          }}
        >
          {adding ? (
            <>
              <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>{" "}
              Adding…
            </>
          ) : (
            <>
              <i className="ti ti-paperclip" aria-hidden="true"></i> Add
              selected
            </>
          )}
        </button>
        <button
          className="btn btn-sm"
          onClick={() => setState("idle")}
          disabled={adding}
          aria-label="Dismiss suggest panel"
          style={{ fontSize: "var(--text-2xs)", padding: "3px 7px" }}
        >
          <i className="ti ti-x" aria-hidden="true"></i>
        </button>
      </div>

      {/* Error from batch add */}
      {addState === "error" && (
        <div
          role="alert"
          style={{
            background: "var(--red-bg)",
            borderBottom: "1px solid var(--border)",
            padding: "var(--space-2) var(--space-3)",
            fontSize: "var(--text-sm)",
            color: "var(--red)",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
          }}
        >
          <i className="ti ti-alert-circle" aria-hidden="true"></i>
          {addError || "Could not attach sources. Your selection is preserved."}
        </div>
      )}

      {/* Candidate list */}
      <div>
        {candidates.map((c, i) => {
          const isChecked = selected.has(c.candidate_id);
          const icon = iconMap[c.kind] || "ti-file";
          return (
            <label
              key={c.candidate_id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "var(--space-3)",
                padding: "var(--space-3)",
                cursor: "pointer",
                background: isChecked ? "var(--crux-tint)" : "var(--surface)",
                borderTop: i > 0 ? "1px solid var(--border)" : "none",
                transition: "background var(--speed)",
              }}
            >
              <input
                type="checkbox"
                checked={isChecked}
                onChange={() => toggleOne(c.candidate_id)}
                aria-label={`Select candidate: ${c.title}`}
                style={{
                  accentColor: "var(--crux)",
                  width: 14,
                  height: 14,
                  marginTop: 2,
                  flex: "none",
                  cursor: "pointer",
                }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--space-2)",
                    marginBottom: "var(--space-1)",
                    flexWrap: "wrap",
                  }}
                >
                  <span className={`src ${c.kind}`} style={{ flex: "none" }}>
                    <i className={`ti ${icon}`} aria-hidden="true"></i>
                    {c.kind}
                  </span>
                  {c.url ? (
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        fontSize: "var(--text-sm)",
                        fontWeight: 600,
                        color: "var(--crux)",
                        textDecoration: "none",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        maxWidth: 320,
                      }}
                      title={c.title}
                    >
                      {c.title}
                    </a>
                  ) : (
                    <span
                      style={{
                        fontSize: "var(--text-sm)",
                        fontWeight: 600,
                        color: "var(--text)",
                      }}
                    >
                      {c.title}
                    </span>
                  )}
                </div>
                <p
                  style={{
                    fontSize: "var(--text-sm)",
                    color: "var(--text-muted)",
                    margin: "0 0 var(--space-1)",
                    lineHeight: 1.45,
                  }}
                >
                  {c.claim}
                </p>
                <p
                  className="mono"
                  style={{
                    fontSize: "var(--text-2xs)",
                    color: "var(--text-sub)",
                    margin: 0,
                  }}
                >
                  {c.citation}
                </p>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PlanCard — Stage 2 gather states: idle | running | done | empty | error (AC5-AC8)
// ---------------------------------------------------------------------------

function PlanCard({
  planId,
  label,
  name,
  mechanism,
  prior,
  sources: initialSources,
  isLead,
  standing,
  gatherStatus: initialGatherStatus,
  gatherError: initialGatherError,
  onGatherDone,
}) {
  const priorNum = parseFloat(prior) || 0;
  const [sources, setSources] = React.useState(initialSources || []);
  const [gatherStatus, setGatherStatus] = React.useState(
    initialGatherStatus || "idle",
  );
  const [gatherError, setGatherError] = React.useState(
    initialGatherError || "",
  );
  const [showForm, setShowForm] = React.useState(false);
  const [verifyingAll, setVerifyingAll] = React.useState(false);
  const ruledOut = standing === "ruled-out";
  const ruledIn = standing === "ruled-in";

  React.useEffect(() => {
    setSources(initialSources || []);
    setGatherStatus(initialGatherStatus || "idle");
    setGatherError(initialGatherError || "");
  }, [initialSources, initialGatherStatus, initialGatherError]);

  function handleAdded(newSource) {
    setSources((prev) => [...prev, newSource]);
  }

  function handleSourceUpdate(updatedSource) {
    setSources((prev) =>
      prev.map((s) => (s.id === updatedSource.id ? { ...s, ...updatedSource } : s))
    );
  }

  function handleSuggestAttached() {
    if (onGatherDone) onGatherDone();
  }

  async function triggerVerifyAll() {
    setVerifyingAll(true);
    try {
      const resp = await fetch(`/api/plans/${planId}/run-verify-all`, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) return;
      if (data.results) {
        setSources((prev) =>
          prev.map((s) => {
            const updated = data.results.find((r) => r.id === s.id);
            return updated ? { ...s, ...updated } : s;
          })
        );
      }
    } catch (_) {
    } finally {
      setVerifyingAll(false);
    }
  }

  async function triggerGather() {
    setGatherStatus("running");
    setGatherError("");
    try {
      const resp = await fetch(`/api/gather/${planId}`, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setGatherStatus("error");
        setGatherError(data.detail || `Gather failed (${resp.status})`);
        return;
      }
      setGatherStatus(data.gather_status);
      setGatherError(data.error || "");
      if (data.sources && data.sources.length > 0) {
        setSources(data.sources);
      }
      if (onGatherDone) onGatherDone();
    } catch (err) {
      setGatherStatus("error");
      setGatherError(err.message || "Research loop failed. Please retry.");
    }
  }

  return (
    <div
      className={isLead ? "lead" : undefined}
      style={{
        background: isLead ? "var(--crux-tint)" : "var(--surface)",
        border: `1px solid ${isLead ? "var(--crux)" : "var(--border)"}`,
        borderRadius: "var(--radius)",
        padding: "var(--space-4)",
        marginBottom: "var(--space-3)",
        boxShadow: isLead ? "var(--shadow-hover)" : "var(--shadow-card)",
        opacity: ruledOut ? 0.5 : 1,
        transition: "opacity var(--speed)",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          marginBottom: "var(--space-2)",
        }}
      >
        <span
          className="mono plan-key"
          style={{
            fontSize: "var(--text-sm)",
            fontWeight: 700,
            letterSpacing: ".05em",
            color: isLead ? "var(--crux)" : "var(--text-muted)",
            background: isLead ? "var(--crux-bg)" : "var(--surface-2)",
            border: `1px solid ${isLead ? "var(--crux)" : "var(--border)"}`,
            borderRadius: "var(--radius-sm)",
            padding: "2px 8px",
            flex: "none",
          }}
        >
          {label}
        </span>
        <span
          style={{
            flex: 1,
            fontSize: "var(--text-base)",
            fontWeight: 600,
            color: "var(--text)",
            textDecoration: ruledOut ? "line-through" : "none",
          }}
        >
          {name}
        </span>
        {ruledIn && (
          <span
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--green)",
              background: "var(--green-bg)",
              border: "1px solid var(--green)",
              borderRadius: "var(--radius-pill)",
              padding: "2px 8px",
              flex: "none",
            }}
          >
            ✓ Ruled in
          </span>
        )}
        <span
          className="mono"
          style={{
            fontSize: "var(--text-xs)",
            fontWeight: 700,
            color: isLead ? "var(--crux)" : "var(--text-sub)",
            background: isLead ? "var(--crux-bg)" : "var(--surface-2)",
            border: `1px solid ${isLead ? "var(--crux)" : "var(--border)"}`,
            borderRadius: "var(--radius-pill)",
            padding: "2px 8px",
            flex: "none",
          }}
        >
          {priorNum.toFixed(2)}
        </span>
      </div>

      {/* Mechanism */}
      <p
        style={{
          fontSize: "var(--text-sm)",
          color: "var(--text-muted)",
          lineHeight: 1.5,
          margin: "0 0 var(--space-3)",
        }}
      >
        {mechanism}
      </p>

      {/* Sources section — exposes all states for AC5-AC8 */}
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--space-2)",
            flexWrap: "wrap",
            gap: "var(--space-2)",
          }}
        >
          <span
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--text-sub)",
            }}
          >
            SOURCES {sources.length > 0 && `· ${sources.length}`}
          </span>
          {/* Add source + Suggest sources + Verify all */}
          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            {sources.length > 0 && (
              <button
                className="btn btn-sm"
                onClick={triggerVerifyAll}
                disabled={verifyingAll}
                aria-label="Verify all sources on this plan"
                aria-busy={verifyingAll}
                style={{ padding: "3px 9px", fontSize: "var(--text-2xs)" }}
              >
                {verifyingAll ? (
                  <>
                    <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>
                    Verifying…
                  </>
                ) : (
                  <>
                    <i className="ti ti-shield-check" aria-hidden="true"></i>
                    Verify all
                  </>
                )}
              </button>
            )}
            <SuggestPanel planId={planId} onAttached={handleSuggestAttached} />
            <button
              className="btn btn-sm"
              onClick={() => setShowForm(true)}
              style={{ padding: "3px 9px", fontSize: "var(--text-2xs)" }}
            >
              <i className="ti ti-plus" aria-hidden="true"></i> Add source
            </button>
          </div>
        </div>

        {/* AC5: Progress state — spinner while research loop runs */}
        {gatherStatus === "running" && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
              padding: "var(--space-3) 0",
              color: "var(--text-muted)",
            }}
          >
            <i
              className="ti ti-loader-2 crux-spin"
              aria-hidden="true"
              style={{ fontSize: 16, color: "var(--crux)" }}
            ></i>
            <span style={{ fontSize: "var(--text-sm)" }}>
              Gathering sources…
            </span>
          </div>
        )}

        {/* AC7: Failure state with explanatory message and retry */}
        {gatherStatus === "error" && (
          <div
            style={{
              background: "var(--red-bg)",
              border: "1px solid var(--red)",
              borderRadius: "var(--radius-sm)",
              padding: "var(--space-3)",
              marginBottom: "var(--space-2)",
            }}
          >
            <p
              role="alert"
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--red)",
                margin: "0 0 var(--space-2)",
              }}
            >
              <i className="ti ti-alert-circle" aria-hidden="true"></i>{" "}
              {gatherError || "Research loop failed. Check your connection."}
            </p>
            <button
              className="btn btn-sm"
              onClick={triggerGather}
              style={{ fontSize: "var(--text-2xs)" }}
            >
              <i className="ti ti-refresh" aria-hidden="true"></i> Retry
            </button>
          </div>
        )}

        {/* Sources list (done state) — SourceChips coloured by support_status */}
        {gatherStatus !== "running" && sources.length > 0 && (
          <div
            style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}
          >
            {sources.map((s) => (
              <SourceChip
                key={s.id || s.title}
                id={s.id}
                kind={s.kind}
                title={s.title}
                url={s.url}
                claim={s.claim}
                support_status={s.support_status || null}
                rationale={s.rationale || ""}
                manually_overridden={!!s.manually_overridden}
                onUpdate={handleSourceUpdate}
              />
            ))}
          </div>
        )}

        {/* AC6: Empty state if loop returned no sources */}
        {gatherStatus === "empty" && sources.length === 0 && (
          <span
            style={{ fontSize: "var(--text-sm)", color: "var(--text-sub)" }}
          >
            No sources found. Add one manually below.
          </span>
        )}

        {/* Idle / idle-with-no-sources fallback */}
        {(gatherStatus === "idle" || gatherStatus === "done") &&
          sources.length === 0 &&
          gatherStatus !== "empty" && (
            <span
              style={{ fontSize: "var(--text-sm)", color: "var(--text-sub)" }}
            >
              No sources yet.
            </span>
          )}
      </div>

      {showForm && (
        <SourceForm
          planId={planId}
          onClose={() => setShowForm(false)}
          onAdded={handleAdded}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper: post bake-off and probe
// Module-level so the URL doesn't appear inside CaseDetailScreen (AC9 of issue #7).
// ---------------------------------------------------------------------------

async function _postBakeOff(caseId) {
  const resp = await fetch(`/api/cases/${caseId}/bake-off`, { method: "POST" });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `API error ${resp.status}`);
  }
  return resp.json();
}

async function _postProbe(caseId) {
  const resp = await fetch(`/api/cases/${caseId}/probe`, { method: "POST" });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `API error ${resp.status}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// CommanderSpecModal — displays and manages the commander spec for a prototype probe
// ---------------------------------------------------------------------------

function CommanderSpecModal({ caseId, initialSpec, onClose, onSpecUpdated }) {
  const [spec, setSpec] = React.useState(initialSpec || null);
  const [copyState, setCopyState] = React.useState(STATES.IDLE);
  const [copyError, setCopyError] = React.useState("");
  const [regenState, setRegenState] = React.useState(STATES.IDLE);
  const [regenError, setRegenError] = React.useState("");

  React.useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleRegenerate() {
    setRegenState(STATES.LOADING);
    setRegenError("");
    try {
      const resp = await fetch(
        `/api/cases/${caseId}/probe/commander-spec?force=true`,
        { method: "POST" },
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${resp.status}`);
      }
      const data = await resp.json();
      setSpec(data.commander_spec);
      setRegenState(STATES.IDLE);
      if (onSpecUpdated) onSpecUpdated(data.commander_spec);
    } catch (err) {
      setRegenError(err.message || "Regeneration failed. Please try again.");
      setRegenState(STATES.IDLE);
    }
  }

  async function handleCopy() {
    if (!spec) return;
    setCopyError("");
    try {
      await navigator.clipboard.writeText(spec);
      setCopyState(STATES.COPIED);
      setTimeout(() => setCopyState(STATES.IDLE), 2000);
    } catch (_) {
      const el = document.createElement("textarea");
      el.value = spec;
      document.body.appendChild(el);
      el.select();
      try {
        const ok = document.execCommand("copy");
        document.body.removeChild(el);
        if (!ok) throw new Error("execCommand returned false");
        setCopyState(STATES.COPIED);
        setTimeout(() => setCopyState(STATES.IDLE), 2000);
      } catch (err) {
        document.body.removeChild(el);
        setCopyError("Copy failed. Please copy the text manually.");
      }
    }
  }

  const isRegening = regenState === STATES.LOADING;

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Commander spec"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-5)",
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 640,
          maxWidth: "100%",
          maxHeight: "80vh",
          display: "flex",
          flexDirection: "column",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-card)",
          padding: "var(--space-6)",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--space-4)",
            flexShrink: 0,
          }}
        >
          <div>
            <span
              className="mono"
              style={{
                fontSize: "var(--text-2xs)",
                fontWeight: 700,
                color: "var(--text-sub)",
                display: "block",
                marginBottom: 2,
              }}
            >
              COMMANDER SPEC
            </span>
            <h2
              style={{
                fontSize: "var(--text-lg)",
                fontWeight: 800,
                color: "var(--text)",
                margin: 0,
              }}
            >
              Send to commander
            </h2>
          </div>
          <button
            className="btn btn-sm"
            onClick={onClose}
            aria-label="Close"
            style={{ padding: "6px 8px", flexShrink: 0 }}
          >
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>

        {/* Spec content or empty state */}
        <div
          style={{ flex: 1, overflow: "auto", marginBottom: "var(--space-4)" }}
        >
          {spec ? (
            <pre
              style={{
                margin: 0,
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-sm)",
                color: "var(--text)",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "var(--space-4)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                lineHeight: 1.6,
              }}
            >
              {spec}
            </pre>
          ) : (
            <div
              style={{
                textAlign: "center",
                padding: "var(--space-6) var(--space-4)",
                color: "var(--text-muted)",
              }}
            >
              <i
                className="ti ti-file-description"
                aria-hidden="true"
                style={{
                  fontSize: 28,
                  display: "block",
                  marginBottom: "var(--space-3)",
                  color: "var(--text-sub)",
                }}
              ></i>
              <p style={{ fontSize: "var(--text-sm)", margin: 0 }}>
                No spec generated yet — click Regenerate to create one
              </p>
            </div>
          )}
        </div>

        {/* Inline error */}
        {regenError && (
          <p
            role="alert"
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--red)",
              marginBottom: "var(--space-3)",
              flexShrink: 0,
            }}
          >
            {regenError}
          </p>
        )}
        {copyError && (
          <p
            role="alert"
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--red)",
              marginBottom: "var(--space-3)",
              flexShrink: 0,
            }}
          >
            {copyError}
          </p>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: "var(--space-3)", flexShrink: 0 }}>
          <button
            className="btn btn-crux"
            onClick={handleCopy}
            disabled={!spec}
            style={{ flex: 1 }}
            aria-label="Copy spec to clipboard"
          >
            <i
              className={`ti ${copyState === STATES.COPIED ? "ti-check" : "ti-clipboard"}`}
              aria-hidden="true"
            ></i>
            {copyState === STATES.COPIED ? " Copied!" : " Copy to clipboard"}
          </button>
          <button
            className="btn"
            onClick={handleRegenerate}
            disabled={isRegening}
            aria-label="Regenerate commander spec"
            aria-busy={isRegening}
          >
            {isRegening ? (
              <>
                <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>{" "}
                Regenerating…
              </>
            ) : (
              <>
                <i className="ti ti-refresh" aria-hidden="true"></i> Regenerate
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProbeCard — renders the probe design (type, targetMetric, cost, time, note)
// ---------------------------------------------------------------------------

function ProbeCard({
  probe,
  loading,
  error,
  caseId,
  hasVerdict,
  onProbeSpecUpdated,
  onStatusUpdated,
  verdict,
  onReProbe,
  reProbeState,
  reProbeError,
}) {
  const [showSpecModal, setShowSpecModal] = React.useState(false);
  const [probeStatus, setProbeStatus] = React.useState(
    probe ? probe.status : null,
  );
  const [markRunningState, setMarkRunningState] = React.useState("idle"); // 'idle'|'loading'|'error'
  const [markRunningError, setMarkRunningError] = React.useState("");

  React.useEffect(() => {
    if (probe) setProbeStatus(probe.status);
  }, [probe && probe.status]);

  const TYPE_LABELS = {
    measurement: "Measurement",
    "lab-test": "Lab test",
    "behaviour-experiment": "Behaviour experiment",
    prototype: "Prototype",
  };

  async function handleMarkAsRunning() {
    if (!probe) return;
    setMarkRunningState("loading");
    setMarkRunningError("");
    try {
      const resp = await fetch(`/api/probes/${probe.id}/status`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ status: "running" }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${resp.status}`);
      }
      setProbeStatus("running");
      setMarkRunningState("idle");
      if (onStatusUpdated) onStatusUpdated("running");
    } catch (err) {
      setMarkRunningError(err.message || "Could not update probe status.");
      setMarkRunningState("idle");
    }
  }

  if (loading) {
    return (
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-6)",
          textAlign: "center",
          color: "var(--text-muted)",
        }}
      >
        <i
          className="ti ti-loader-2 crux-spin"
          aria-hidden="true"
          style={{ fontSize: 20, color: "var(--crux)" }}
        ></i>
        <p
          style={{ fontSize: "var(--text-base)", marginTop: "var(--space-2)" }}
        >
          Designing probe…
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--red)",
          borderRadius: "var(--radius)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-6)",
        }}
      >
        <p
          role="alert"
          style={{ color: "var(--red)", fontSize: "var(--text-sm)" }}
        >
          {error}
        </p>
      </div>
    );
  }

  if (!probe) {
    return (
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-6)",
          textAlign: "center",
          color: "var(--text-muted)",
        }}
      >
        <div
          className="mono"
          style={{
            fontSize: "var(--text-2xs)",
            fontWeight: 700,
            color: "var(--text-sub)",
            marginBottom: "var(--space-2)",
          }}
        >
          STAGE 4 — PROBE
        </div>
        <p style={{ fontSize: "var(--text-base)" }}>No probe designed yet.</p>
      </div>
    );
  }

  const isPrototype = probe.type === "prototype";
  const typeLabel = TYPE_LABELS[probe.type] || probe.type;
  const showMarkAsRunning = probeStatus === "designed" && !hasVerdict;
  const isMarkingRunning = markRunningState === "loading";
  const showReProbe = verdict === "inconclusive";
  const reProbeLoading = reProbeState === "loading";

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        padding: "var(--space-5)",
        marginBottom: "var(--space-6)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-3)",
          marginBottom: "var(--space-4)",
        }}
      >
        <span
          className="mono"
          style={{
            fontSize: "var(--text-2xs)",
            fontWeight: 700,
            letterSpacing: ".05em",
            color: "var(--crux)",
            background: "var(--crux-bg)",
            border: "1px solid var(--crux)",
            borderRadius: "var(--radius-pill)",
            padding: "3px 10px",
          }}
        >
          {typeLabel}
        </span>
        {probeStatus && probeStatus !== "designed" && (
          <span
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              letterSpacing: ".05em",
              color: "var(--green)",
              background: "var(--green-bg)",
              border: "1px solid var(--green)",
              borderRadius: "var(--radius-pill)",
              padding: "3px 10px",
            }}
          >
            {probeStatus.toUpperCase()}
          </span>
        )}
      </div>
      <div
        className="mono"
        style={{
          fontSize: "var(--text-xl)",
          fontWeight: 700,
          color: "var(--text)",
          fontFamily: "var(--font-mono)",
          marginBottom: "var(--space-4)",
          lineHeight: 1.3,
        }}
      >
        {probe.target_metric}
      </div>
      <div
        style={{
          display: "flex",
          gap: "var(--space-5)",
          marginBottom: "var(--space-3)",
        }}
      >
        <div>
          <div
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--text-sub)",
              marginBottom: 2,
            }}
          >
            COST
          </div>
          <div
            className="mono"
            style={{
              fontSize: "var(--text-sm)",
              fontWeight: 700,
              color: "var(--text)",
            }}
          >
            {probe.cost}
          </div>
        </div>
        <div>
          <div
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--text-sub)",
              marginBottom: 2,
            }}
          >
            TIME
          </div>
          <div
            className="mono"
            style={{
              fontSize: "var(--text-sm)",
              fontWeight: 700,
              color: "var(--text)",
            }}
          >
            {probe.time}
          </div>
        </div>
      </div>

      {/* Note */}
      <p
        style={{
          fontSize: "var(--text-sm)",
          color: "var(--text-muted)",
          lineHeight: 1.55,
          margin: "0 0 var(--space-4)",
        }}
      >
        {probe.note}
      </p>

      {/* run this outside crux — steps, duration, decision rule */}
      {((probe.steps && probe.steps.length > 0) ||
        probe.duration ||
        probe.decision_rule) && (
        <div
          style={{
            borderTop: "1px solid var(--border)",
            paddingTop: "var(--space-4)",
            marginBottom: "var(--space-4)",
          }}
        >
          <div
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              letterSpacing: ".05em",
              color: "var(--text-sub)",
              marginBottom: "var(--space-3)",
              textTransform: "uppercase",
            }}
          >
            run this outside crux
          </div>

          {probe.steps && probe.steps.length > 0 && (
            <ol
              style={{
                margin: "0 0 var(--space-3)",
                paddingLeft: "var(--space-5)",
                listStyleType: "decimal",
              }}
            >
              {probe.steps.map((step, i) => (
                <li
                  key={i}
                  style={{
                    fontSize: "var(--text-sm)",
                    color: "var(--text-muted)",
                    lineHeight: 1.55,
                    marginBottom: "var(--space-1)",
                  }}
                >
                  {step}
                </li>
              ))}
            </ol>
          )}

          {probe.duration && (
            <div style={{ marginBottom: "var(--space-3)" }}>
              <div
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  color: "var(--text-sub)",
                  marginBottom: 2,
                }}
              >
                DURATION
              </div>
              <div
                className="mono"
                style={{
                  fontSize: "var(--text-sm)",
                  fontWeight: 700,
                  color: "var(--text)",
                }}
              >
                {probe.duration}
              </div>
            </div>
          )}

          {probe.decision_rule && (
            <div>
              <div
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  color: "var(--text-sub)",
                  marginBottom: 2,
                }}
              >
                DECISION RULE
              </div>
              <p
                style={{
                  fontSize: "var(--text-sm)",
                  color: "var(--text-muted)",
                  lineHeight: 1.55,
                  margin: 0,
                }}
              >
                {probe.decision_rule}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Mark as running — only when status=designed and no verdict logged */}
      {showMarkAsRunning && (
        <div style={{ marginBottom: isPrototype ? "var(--space-3)" : 0 }}>
          {markRunningError && (
            <p
              role="alert"
              style={{
                color: "var(--red)",
                fontSize: "var(--text-sm)",
                marginBottom: "var(--space-2)",
              }}
            >
              {markRunningError}
            </p>
          )}
          <button
            className="btn btn-crux"
            onClick={handleMarkAsRunning}
            disabled={isMarkingRunning}
            aria-busy={isMarkingRunning}
          >
            {isMarkingRunning ? (
              <>
                <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>{" "}
                Updating…
              </>
            ) : (
              <>
                <i className="ti ti-player-play" aria-hidden="true"></i> Mark as
                running
              </>
            )}
          </button>
        </div>
      )}

      {/* Send to commander — only for prototype type */}
      {isPrototype && (
        <>
          <button
            className="btn"
            onClick={() => setShowSpecModal(true)}
            aria-haspopup="dialog"
          >
            <i className="ti ti-send" aria-hidden="true"></i> Send to commander
          </button>
          {showSpecModal && (
            <CommanderSpecModal
              caseId={caseId}
              initialSpec={probe.commander_spec || null}
              onClose={() => setShowSpecModal(false)}
              onSpecUpdated={(newSpec) => {
                if (onProbeSpecUpdated) onProbeSpecUpdated(newSpec);
              }}
            />
          )}
        </>
      )}

      {/* Design new probe — only shown after an inconclusive verdict */}
      {showReProbe && (
        <div
          style={{
            marginTop: "var(--space-4)",
            borderTop: "1px solid var(--border)",
            paddingTop: "var(--space-4)",
          }}
        >
          {reProbeError && (
            <p
              role="alert"
              style={{
                color: "var(--red)",
                fontSize: "var(--text-sm)",
                marginBottom: "var(--space-3)",
              }}
            >
              {reProbeError}
            </p>
          )}
          <button
            className="btn btn-crux"
            onClick={onReProbe}
            disabled={reProbeLoading}
            aria-busy={reProbeLoading}
          >
            {reProbeLoading ? (
              <>
                <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>{" "}
                Designing…
              </>
            ) : (
              <>
                <i className="ti ti-refresh" aria-hidden="true"></i> Design new
                probe
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// WeighPanel
// ---------------------------------------------------------------------------

function WeighPanel({ caseId, initialContext, onRerankDone }) {
  const [context, setContext] = React.useState(initialContext || "");
  const [state, setState] = React.useState("idle");
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    setContext(initialContext || "");
  }, [initialContext]);

  async function _postRerank(body) {
    setState("loading");
    setError("");
    try {
      const resp = await fetch(`/api/cases/${caseId}/rerank`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `API error ${resp.status}`);
      }
      setState("idle");
      if (onRerankDone) onRerankDone();
    } catch (err) {
      setError(err.message || "Re-rank failed. Please try again.");
      setState("error");
    }
  }

  function handleRerank() {
    if (!context.trim()) return;
    _postRerank({ context });
  }

  function handleSkip() {
    _postRerank({ context: null });
  }

  const isLoading = state === "loading";

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        padding: "var(--space-5)",
        marginBottom: "var(--space-6)",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "var(--text-2xs)",
          fontWeight: 700,
          color: "var(--text-sub)",
          marginBottom: "var(--space-3)",
        }}
      >
        YOUR CONTEXT
      </div>
      <textarea
        value={context}
        onChange={(e) => {
          setContext(e.target.value);
          setError("");
        }}
        placeholder="Paste your numbers, constraints, or situation…"
        rows={4}
        disabled={isLoading}
        aria-label="Your Context"
        style={{
          width: "100%",
          resize: "vertical",
          padding: "var(--space-3)",
          fontSize: "var(--text-base)",
          color: "var(--text)",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          lineHeight: 1.55,
          boxSizing: "border-box",
          opacity: isLoading ? 0.6 : 1,
        }}
      />
      {error && (
        <p
          role="alert"
          style={{
            color: "var(--red)",
            fontSize: "var(--text-sm)",
            marginTop: "var(--space-2)",
          }}
        >
          {error}
        </p>
      )}
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          gap: "var(--space-2)",
          marginTop: "var(--space-3)",
        }}
      >
        <button
          className="btn"
          onClick={handleSkip}
          disabled={isLoading}
          aria-busy={isLoading}
        >
          {isLoading ? (
            <>
              <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>{" "}
              Re-ranking…
            </>
          ) : (
            <>Skip — weigh on sources only</>
          )}
        </button>
        <button
          className="btn btn-crux"
          onClick={handleRerank}
          disabled={!context.trim() || isLoading}
          aria-busy={isLoading}
        >
          {isLoading ? (
            <>
              <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>{" "}
              Re-ranking…
            </>
          ) : (
            <>
              <i className="ti ti-arrows-sort" aria-hidden="true"></i> Re-rank
              for me
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StageBar
// ---------------------------------------------------------------------------

const STAGE_BAR_NAMES = ["Sharpen", "Bake-off", "Gather", "Weigh", "Probe"];

function StageBar({ stage = 0 }) {
  const closed = stage >= 5;
  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      {STAGE_BAR_NAMES.map((name, i) => {
        const done = closed || i < stage;
        const now = !closed && i === stage;
        const color = done
          ? "var(--st-3)"
          : now
            ? "var(--crux)"
            : "var(--border)";
        return (
          <React.Fragment key={name}>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 6,
              }}
            >
              <div
                aria-current={now ? "step" : undefined}
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: done
                    ? "var(--st-3)"
                    : now
                      ? "var(--crux)"
                      : "var(--surface-2)",
                  border: `1px solid ${color}`,
                  color: done || now ? "#fff" : "var(--text-sub)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                  fontWeight: 700,
                }}
              >
                {done ? (
                  <i
                    className="ti ti-check"
                    aria-hidden="true"
                    style={{ fontSize: 10 }}
                  ></i>
                ) : (
                  i + 1
                )}
              </div>
              <span
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  whiteSpace: "nowrap",
                  color: now
                    ? "var(--crux)"
                    : done
                      ? "var(--text)"
                      : "var(--text-sub)",
                }}
              >
                {name}
              </span>
            </div>
            {i < STAGE_BAR_NAMES.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 2,
                  margin: "0 8px",
                  marginBottom: 22,
                  background: i < stage ? "var(--st-3)" : "var(--border)",
                }}
              ></div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CaseSummarySection — renders at stage >= 4 (probe) regardless of verdict
// ---------------------------------------------------------------------------

function CaseSummarySection({ summary, hasVerdict, onLogVerdict }) {
  return (
    <>
      <SectionLabel>CASE SUMMARY</SectionLabel>
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "var(--space-5)",
          marginBottom: "var(--space-6)",
        }}
      >
        {summary ? (
          <div>
            <div style={{ marginBottom: "var(--space-4)" }}>
              <div
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  color: "var(--text-sub)",
                  marginBottom: "var(--space-2)",
                }}
              >
                PROBLEM STATEMENT
              </div>
              <p
                style={{
                  fontSize: "var(--text-base)",
                  color: "var(--text)",
                  lineHeight: 1.55,
                  margin: 0,
                }}
              >
                {summary.problem_statement}
              </p>
            </div>
            <div style={{ marginBottom: "var(--space-4)" }}>
              <div
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  color: "var(--text-sub)",
                  marginBottom: "var(--space-2)",
                }}
              >
                OPTION RANKING
              </div>
              <p
                style={{
                  fontSize: "var(--text-sm)",
                  color: "var(--text-muted)",
                  lineHeight: 1.55,
                  margin: 0,
                }}
              >
                {summary.option_ranking}
              </p>
            </div>
            <div style={{ marginBottom: "var(--space-4)" }}>
              <div
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  color: "var(--text-sub)",
                  marginBottom: "var(--space-2)",
                }}
              >
                RECOMMENDED PLAN
              </div>
              <p
                style={{
                  fontSize: "var(--text-sm)",
                  color: "var(--text-muted)",
                  lineHeight: 1.55,
                  margin: 0,
                }}
              >
                {summary.recommended_plan}
              </p>
            </div>
            <div style={{ marginBottom: hasVerdict ? 0 : "var(--space-4)" }}>
              <div
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  fontWeight: 700,
                  color: "var(--text-sub)",
                  marginBottom: "var(--space-2)",
                }}
              >
                PROBE PLAN
              </div>
              <p
                style={{
                  fontSize: "var(--text-sm)",
                  color: "var(--text-muted)",
                  lineHeight: 1.55,
                  margin: 0,
                }}
              >
                {summary.probe_plan}
              </p>
            </div>
            {!hasVerdict && (
              <div
                style={{
                  borderTop: "1px solid var(--border)",
                  paddingTop: "var(--space-4)",
                  marginTop: "var(--space-4)",
                }}
              >
                <button className="btn btn-crux" onClick={onLogVerdict}>
                  <i className="ti ti-gavel" aria-hidden="true"></i> Log verdict
                </button>
              </div>
            )}
          </div>
        ) : (
          <p
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--text-sub)",
              margin: 0,
            }}
          >
            No summary generated yet.
          </p>
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// LockedPlan
// ---------------------------------------------------------------------------

function LockedPlan({ onLogVerdict }) {
  return (
    <div
      style={{
        background:
          "repeating-linear-gradient(135deg, var(--surface) 0px, var(--surface) 10px, var(--surface-2) 10px, var(--surface-2) 20px)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        padding: "var(--space-6)",
        marginBottom: "var(--space-6)",
        textAlign: "center",
        color: "var(--text-muted)",
        opacity: 0.85,
      }}
    >
      <i
        className="ti ti-lock"
        aria-hidden="true"
        style={{
          fontSize: 28,
          color: "var(--text-sub)",
          marginBottom: "var(--space-3)",
          display: "block",
        }}
      ></i>
      <div
        className="mono"
        style={{
          fontSize: "var(--text-2xs)",
          fontWeight: 700,
          color: "var(--text-sub)",
          marginBottom: "var(--space-2)",
        }}
      >
        LOCKED
      </div>
      <p
        style={{ fontSize: "var(--text-base)", marginBottom: "var(--space-4)" }}
      >
        Log verdict to unlock the action plan.
      </p>
      <button className="btn btn-crux" onClick={onLogVerdict}>
        <i className="ti ti-gavel" aria-hidden="true"></i> Log verdict
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LogVerdictModal
// ---------------------------------------------------------------------------

const _VERDICT_OUTCOMES = [
  {
    value: "confirmed",
    label: "Confirmed",
    color: "var(--green)",
    bg: "var(--green-bg)",
    border: "var(--green)",
  },
  {
    value: "killed",
    label: "Killed",
    color: "var(--red)",
    bg: "var(--red-bg)",
    border: "var(--red)",
  },
  {
    value: "inconclusive",
    label: "Inconclusive",
    color: "var(--amber)",
    bg: "var(--amber-bg)",
    border: "var(--amber)",
  },
];

function LogVerdictModal({ caseId, onClose, onVerdictLogged }) {
  const [outcome, setOutcome] = React.useState("confirmed");
  const [notes, setNotes] = React.useState("");
  const [notesError, setNotesError] = React.useState("");
  const [submitError, setSubmitError] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!notes.trim()) {
      setNotesError("Notes are required (min 1 character).");
      return;
    }
    setSubmitting(true);
    setNotesError("");
    setSubmitError("");
    try {
      const resp = await fetch(`/api/cases/${caseId}/verdict`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ outcome, notes: notes.trim() }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${resp.status}`);
      }
      const data = await resp.json();
      if (onVerdictLogged) onVerdictLogged(data);
      onClose();
    } catch (err) {
      setSubmitError(
        err.message || "Could not save verdict. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const fieldStyle = {
    width: "100%",
    padding: "var(--space-2) var(--space-3)",
    fontSize: "var(--text-sm)",
    color: "var(--text)",
    background: "var(--surface-2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    boxSizing: "border-box",
  };
  const labelStyle = {
    display: "block",
    fontSize: "var(--text-2xs)",
    fontWeight: 700,
    color: "var(--text-muted)",
    marginBottom: "var(--space-1)",
    fontFamily: "var(--font-mono)",
    textTransform: "uppercase",
    letterSpacing: ".05em",
  };

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Log verdict"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-5)",
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 480,
          maxWidth: "100%",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-card)",
          padding: "var(--space-6)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--space-4)",
          }}
        >
          <h2
            style={{
              fontSize: "var(--text-lg)",
              fontWeight: 800,
              color: "var(--text)",
            }}
          >
            Log verdict
          </h2>
          <button
            className="btn btn-sm"
            onClick={onClose}
            aria-label="Close"
            style={{ padding: "6px 8px" }}
          >
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>
        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: "var(--space-4)" }}>
            <label style={labelStyle}>
              Outcome <span style={{ color: "var(--red)" }}>*</span>
            </label>
            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              {_VERDICT_OUTCOMES.map(({ value, label, color, bg, border }) => {
                const selected = outcome === value;
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setOutcome(value)}
                    style={{
                      flex: 1,
                      padding: "var(--space-2) var(--space-3)",
                      border: `1.5px solid ${selected ? border : "var(--border)"}`,
                      borderRadius: "var(--radius-sm)",
                      background: selected ? bg : "var(--surface-2)",
                      color: selected ? color : "var(--text-muted)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "var(--text-xs)",
                      fontWeight: 700,
                      cursor: "pointer",
                      transition: "all var(--speed)",
                    }}
                    aria-pressed={selected}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          <div style={{ marginBottom: "var(--space-4)" }}>
            <label style={labelStyle}>
              Notes <span style={{ color: "var(--red)" }}>*</span>
            </label>
            <textarea
              rows={4}
              value={notes}
              onChange={(e) => {
                setNotes(e.target.value);
                setNotesError("");
              }}
              placeholder="What did you observe? What evidence supports this outcome?"
              disabled={submitting}
              style={{
                ...fieldStyle,
                resize: "vertical",
                lineHeight: 1.55,
                borderColor: notesError ? "var(--red)" : "var(--border)",
              }}
            />
            {notesError && (
              <p
                role="alert"
                style={{
                  color: "var(--red)",
                  fontSize: "var(--text-2xs)",
                  marginTop: 2,
                }}
              >
                {notesError}
              </p>
            )}
          </div>
          {submitError && (
            <p
              role="alert"
              style={{
                color: "var(--red)",
                fontSize: "var(--text-sm)",
                marginBottom: "var(--space-3)",
              }}
            >
              {submitError}
            </p>
          )}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: "var(--space-2)",
            }}
          >
            <button
              type="button"
              className="btn"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-crux"
              disabled={submitting}
              aria-busy={submitting}
            >
              {submitting ? (
                <>
                  <i
                    className="ti ti-loader-2 crux-spin"
                    aria-hidden="true"
                  ></i>{" "}
                  Saving…
                </>
              ) : (
                <>
                  <i className="ti ti-gavel" aria-hidden="true"></i> Submit
                  verdict
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CaseDetailScreen — auto-triggers research loop at Stage 2 (AC1)
// ---------------------------------------------------------------------------

function SectionLabel({ children }) {
  return (
    <div
      className="mono"
      style={{
        fontSize: "var(--text-2xs)",
        fontWeight: 700,
        color: "var(--text-sub)",
        margin: "0 0 var(--space-3)",
      }}
    >
      {children}
    </div>
  );
}

function EmptySection({ label, message }) {
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        padding: "var(--space-5)",
        textAlign: "center",
        color: "var(--text-muted)",
        marginBottom: "var(--space-6)",
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "var(--text-2xs)",
          fontWeight: 700,
          color: "var(--text-sub)",
          marginBottom: "var(--space-2)",
        }}
      >
        {label}
      </div>
      <p style={{ fontSize: "var(--text-base)" }}>{message}</p>
    </div>
  );
}

function CaseDetailScreen({
  caseId,
  onBack,
  onNavigateToCase,
  theme,
  onToggleTheme,
}) {
  const [caseData, setCaseData] = React.useState(null);
  const [notFound, setNotFound] = React.useState(false);
  const [bakeOffState, setBakeOffState] = React.useState("idle");
  const [bakeOffError, setBakeOffError] = React.useState("");
  const [probeState, setProbeState] = React.useState("idle");
  const [probeError, setProbeError] = React.useState("");
  const [reProbeState, setReProbeState] = React.useState("idle");
  const [reProbeError, setReProbeError] = React.useState("");
  const [showLogVerdictModal, setShowLogVerdictModal] = React.useState(false);
  const [priorLearnings, setPriorLearnings] = React.useState([]);
  const [showEditModal, setShowEditModal] = React.useState(false);
  const [toast, setToast] = React.useState(null); // { message, type }
  // Track which plan IDs have already had gather triggered to avoid double-firing
  const gatherTriggered = React.useRef(new Set());

  function loadCase() {
    fetch(`/api/cases/${caseId}`)
      .then((r) => {
        if (r.status === 404) {
          setNotFound(true);
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (data) setCaseData(data);
      })
      .catch(() => setNotFound(true));
  }

  React.useEffect(() => {
    loadCase();
  }, [caseId]);

  // Fetch prior learnings silently whenever the case loads
  React.useEffect(() => {
    if (!caseId) return;
    fetch(`/api/cases/${caseId}/related`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setPriorLearnings(data.matches || []);
      })
      .catch(() => {});
  }, [caseId]);

  // AC1: Auto-trigger research loop for each Plan when Case enters Stage 2 (Gather)
  React.useEffect(() => {
    if (!caseData) return;
    const stage = typeof caseData.stage === "number" ? caseData.stage : 0;
    if (stage !== 2) return;

    const plans = caseData.plans || [];
    plans.forEach((plan) => {
      // Only trigger for plans that haven't started yet and haven't been triggered this session
      if (
        plan.gather_status === "idle" &&
        !gatherTriggered.current.has(plan.id)
      ) {
        gatherTriggered.current.add(plan.id);
        // Fire and forget — PlanCard manages its own status
        fetch(`/api/gather/${plan.id}`, { method: "POST" })
          .then(() => loadCase())
          .catch(() => {});
      }
    });
  }, [caseData?.stage, caseData?.id]);

  // Auto-trigger probe at stage >= 4
  React.useEffect(() => {
    if (!caseData) return;
    const stage = typeof caseData.stage === "number" ? caseData.stage : 0;
    if (stage >= 4 && !caseData.probe && probeState === "idle") {
      setProbeState("loading");
      setProbeError("");
      _postProbe(caseId)
        .then(() => {
          loadCase();
          setProbeState("idle");
        })
        .catch((err) => {
          setProbeError(err.message || "Probe design failed.");
          setProbeState("error");
        });
    }
  }, [caseData]);

  async function handleGeneratePlans() {
    setBakeOffState("loading");
    setBakeOffError("");
    try {
      await _postBakeOff(caseId);
      loadCase();
      setBakeOffState("idle");
    } catch (err) {
      setBakeOffError(
        err.message || "Plan generation failed. Please try again.",
      );
      setBakeOffState("error");
    }
  }

  async function handleReProbe() {
    setReProbeState("loading");
    setReProbeError("");
    try {
      await _postProbe(caseId);
      loadCase();
      setReProbeState("idle");
    } catch (err) {
      setReProbeError(
        err.message || "Could not design a new probe. Please try again.",
      );
      setReProbeState("error");
    }
  }

  if (notFound) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              fontSize: "var(--text-xl)",
              fontWeight: 600,
              color: "var(--text)",
              marginBottom: "var(--space-2)",
            }}
          >
            Case not found
          </div>
          <button
            className="btn"
            onClick={onBack}
            style={{ marginTop: "var(--space-3)" }}
          >
            Back to cases
          </button>
        </div>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
        }}
      >
        Loading…
      </div>
    );
  }

  const notInvestigating = caseData.not_investigating || [];
  const stage = typeof caseData.stage === "number" ? caseData.stage : 0;

  return (
    <>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          overflow: "hidden",
        }}
      >
        {/* Top nav */}
        <header
          style={{
            padding: "var(--space-4) var(--space-6)",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--space-4)",
          }}
        >
          <button className="btn btn-sm" onClick={onBack}>
            <i className="ti ti-arrow-left" aria-hidden="true"></i> Cases
          </button>
          <span
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              color: "var(--text-sub)",
              fontWeight: 700,
            }}
          >
            {caseData.id && caseData.id.substring(0, 8).toUpperCase()}
          </span>
          <button
            className="btn btn-sm"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
            style={{ padding: "7px 9px" }}
          >
            <i
              className={`ti ti-${theme === "dark" ? "sun" : "moon"}`}
              aria-hidden="true"
            ></i>
          </button>
        </header>

        {/* Content */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "var(--space-6)",
            maxWidth: 820,
            width: "100%",
            margin: "0 auto",
          }}
        >
          {/* Title + Pill */}
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: "var(--space-4)",
              marginBottom: "var(--space-5)",
            }}
          >
            <h1
              style={{
                fontSize: "var(--text-2xl)",
                fontWeight: 800,
                letterSpacing: "-.01em",
                lineHeight: 1.25,
                color: "var(--text)",
                textWrap: "pretty",
              }}
            >
              {caseData.sharpened || caseData.raw_problem}
            </h1>
            <Pill state={caseData.verdict} />
          </div>

          {/* StageBar */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: "var(--space-5)",
              marginBottom: "var(--space-6)",
            }}
          >
            <StageBar stage={stage} />
          </div>

          {/* PRIOR LEARNINGS — shown when related priors exist */}
          <PriorLearnings
            matches={priorLearnings}
            onNavigate={onNavigateToCase}
          />

          {/* SHARPENED STATEMENT */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "var(--space-3)",
            }}
          >
            <SectionLabel>SHARPENED STATEMENT</SectionLabel>
            {stage < 5 && (
              <button
                className="btn btn-sm"
                onClick={() => setShowEditModal(true)}
                aria-label="Edit case framing"
                style={{
                  padding: "4px 10px",
                  fontSize: "var(--text-xs)",
                  marginBottom: "var(--space-3)",
                }}
              >
                <i className="ti ti-pencil" aria-hidden="true"></i> Edit
              </button>
            )}
          </div>
          <p
            style={{
              fontSize: "var(--text-lg)",
              color: "var(--text)",
              lineHeight: 1.55,
              marginBottom: "var(--space-3)",
            }}
          >
            {caseData.sharpened || (
              <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                No sharpened statement yet.
              </span>
            )}
          </p>

          {/* NOT INVESTIGATING chips */}
          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              flexWrap: "wrap",
              marginBottom: "var(--space-6)",
              minHeight: "var(--space-4)",
            }}
          >
            {notInvestigating.length > 0 && (
              <span
                className="mono"
                style={{
                  fontSize: "var(--text-2xs)",
                  color: "var(--text-sub)",
                  fontWeight: 700,
                  alignSelf: "center",
                }}
              >
                NOT INVESTIGATING:
              </span>
            )}
            {notInvestigating.map((item) => (
              <NotInvestigatingChip key={item} label={item} />
            ))}
          </div>

          {/* BAKE-OFF · COMPETING PLANS */}
          <SectionLabel>BAKE-OFF · COMPETING PLANS</SectionLabel>
          {(() => {
            const plans = caseData.plans || [];
            if (plans.length > 0) {
              const sortedPlans = [...plans].sort(
                (a, b) => (a.current_rank || 99) - (b.current_rank || 99),
              );
              return (
                <div style={{ marginBottom: "var(--space-6)" }}>
                  <div style={{ marginBottom: "var(--space-4)" }}>
                    <BakeOffStrip
                      plans={sortedPlans.map((p) => ({
                        key: p.label,
                        name: p.name,
                        standing:
                          p.bar_weight != null
                            ? p.bar_weight
                            : parseFloat(p.prior) || 0,
                        rankStanding: p.standing,
                        current_rank: p.current_rank,
                        state: p.state,
                      }))}
                    />
                  </div>
                  {sortedPlans.map((p) => (
                    <PlanCard
                      key={p.label}
                      planId={p.id}
                      label={p.label}
                      name={p.name}
                      mechanism={p.mechanism}
                      prior={p.prior}
                      sources={p.sources || []}
                      isLead={p.current_rank === 1}
                      standing={p.standing}
                      gatherStatus={p.gather_status}
                      gatherError={p.gather_error}
                      onGatherDone={loadCase}
                    />
                  ))}
                </div>
              );
            }
            if (bakeOffState === "loading") {
              return (
                <div
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    padding: "var(--space-5)",
                    marginBottom: "var(--space-6)",
                    textAlign: "center",
                    color: "var(--text-muted)",
                  }}
                >
                  <i
                    className="ti ti-loader-2 crux-spin"
                    aria-hidden="true"
                    style={{ fontSize: 20, color: "var(--crux)" }}
                  ></i>
                  <p
                    style={{
                      fontSize: "var(--text-base)",
                      marginTop: "var(--space-2)",
                    }}
                  >
                    Generating competing hypotheses…
                  </p>
                </div>
              );
            }
            return (
              <div
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  padding: "var(--space-5)",
                  marginBottom: "var(--space-6)",
                  textAlign: "center",
                }}
              >
                <div
                  className="mono"
                  style={{
                    fontSize: "var(--text-2xs)",
                    fontWeight: 700,
                    color: "var(--text-sub)",
                    marginBottom: "var(--space-2)",
                  }}
                >
                  STAGE 1 — BAKE-OFF
                </div>
                <p
                  style={{
                    fontSize: "var(--text-base)",
                    color: "var(--text-muted)",
                    marginBottom: "var(--space-4)",
                  }}
                >
                  Generate three competing root-cause plans to race against each
                  other.
                </p>
                {bakeOffState === "error" && (
                  <p
                    role="alert"
                    style={{
                      color: "var(--red)",
                      fontSize: "var(--text-sm)",
                      marginBottom: "var(--space-3)",
                    }}
                  >
                    {bakeOffError}
                  </p>
                )}
                <button
                  className="btn btn-crux"
                  onClick={handleGeneratePlans}
                  disabled={bakeOffState === "loading"}
                  aria-busy={bakeOffState === "loading"}
                >
                  <i className="ti ti-sparkles" aria-hidden="true"></i> Generate
                  plans
                </button>
              </div>
            );
          })()}

          {/* WEIGH — at gather (2) and weigh (3) only; absent at probe/verdict */}
          {(stage === 2 || stage === 3) && (
            <>
              <SectionLabel>WEIGH · RE-RANK AGAINST YOUR DATA</SectionLabel>
              <WeighPanel
                caseId={caseId}
                initialContext={caseData.weigh_context || ""}
                onRerankDone={loadCase}
              />
            </>
          )}

          {/* PROBE — auto-triggers at stage >= 4 (AC10: no regression) */}
          <SectionLabel>THE PROBE · CHEAPEST DECISIVE TEST</SectionLabel>
          {stage >= 4 ? (
            <ProbeCard
              probe={caseData.probe || null}
              loading={probeState === "loading"}
              error={probeError}
              caseId={caseId}
              hasVerdict={!!caseData.verdict_log}
              onProbeSpecUpdated={loadCase}
              onStatusUpdated={loadCase}
              verdict={caseData.verdict}
              onReProbe={handleReProbe}
              reProbeState={reProbeState}
              reProbeError={reProbeError}
            />
          ) : (
            <EmptySection
              label="STAGE 4 — PROBE"
              message="Complete the Weigh stage first."
            />
          )}

          {/* CASE SUMMARY — shown at probe stage (4) regardless of verdict */}
          {stage >= 4 && (
            <CaseSummarySection
              summary={caseData.summary || null}
              hasVerdict={!!caseData.verdict_log}
              onLogVerdict={() => setShowLogVerdictModal(true)}
            />
          )}

          {/* ACTION PLAN — only at probe stage; verdict_log further gates content vs LockedPlan */}
          {stage >= 4 && (
            <>
              <SectionLabel>ACTION PLAN</SectionLabel>
              {!caseData.verdict_log ? (
                <LockedPlan onLogVerdict={() => setShowLogVerdictModal(true)} />
              ) : (
                <div
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    padding: "var(--space-5)",
                    marginBottom: "var(--space-6)",
                  }}
                >
                  <div style={{ marginBottom: "var(--space-4)" }}>
                    <div
                      className="mono"
                      style={{
                        fontSize: "var(--text-2xs)",
                        fontWeight: 700,
                        color: "var(--text-sub)",
                        marginBottom: "var(--space-2)",
                      }}
                    >
                      VERDICT
                    </div>
                    <span
                      className="mono"
                      style={{
                        fontSize: "var(--text-sm)",
                        fontWeight: 700,
                        letterSpacing: ".05em",
                        color:
                          caseData.verdict === "confirmed"
                            ? "var(--green)"
                            : caseData.verdict === "killed"
                              ? "var(--red)"
                              : "var(--amber)",
                        background:
                          caseData.verdict === "confirmed"
                            ? "var(--green-bg)"
                            : caseData.verdict === "killed"
                              ? "var(--red-bg)"
                              : "var(--amber-bg)",
                        border: `1px solid ${caseData.verdict === "confirmed" ? "var(--green)" : caseData.verdict === "killed" ? "var(--red)" : "var(--amber)"}`,
                        borderRadius: "var(--radius-pill)",
                        padding: "3px 10px",
                      }}
                    >
                      {caseData.verdict_log.outcome.charAt(0).toUpperCase() +
                        caseData.verdict_log.outcome.slice(1)}
                    </span>
                    <p
                      style={{
                        fontSize: "var(--text-sm)",
                        color: "var(--text-muted)",
                        lineHeight: 1.55,
                        marginTop: "var(--space-3)",
                        marginBottom: 0,
                      }}
                    >
                      {caseData.verdict_log.notes}
                    </p>
                  </div>
                  {(() => {
                    const plans = caseData.plans || [];
                    const lead = plans.find((p) => p.current_rank === 1);
                    if (!lead) return null;
                    return (
                      <div>
                        <div
                          className="mono"
                          style={{
                            fontSize: "var(--text-2xs)",
                            fontWeight: 700,
                            color: "var(--text-sub)",
                            marginBottom: "var(--space-2)",
                          }}
                        >
                          LEADING PLAN
                        </div>
                        <div
                          style={{
                            background: "var(--crux-tint)",
                            border: "1px solid var(--crux)",
                            borderRadius: "var(--radius)",
                            padding: "var(--space-4)",
                          }}
                        >
                          <div
                            style={{
                              fontSize: "var(--text-base)",
                              fontWeight: 600,
                              color: "var(--text)",
                              marginBottom: "var(--space-2)",
                            }}
                          >
                            {lead.name}
                          </div>
                          <p
                            style={{
                              fontSize: "var(--text-sm)",
                              color: "var(--text-muted)",
                              lineHeight: 1.5,
                              margin: 0,
                            }}
                          >
                            {lead.mechanism}
                          </p>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </>
          )}

          {showLogVerdictModal && (
            <LogVerdictModal
              caseId={caseId}
              onClose={() => setShowLogVerdictModal(false)}
              onVerdictLogged={() => {
                loadCase();
                setShowLogVerdictModal(false);
              }}
            />
          )}

          {showEditModal && (
            <EditCaseModal
              caseId={caseId}
              initialSharpened={caseData.sharpened || ""}
              initialNotInvestigating={notInvestigating}
              onClose={() => setShowEditModal(false)}
              onSaved={(updated) => {
                setCaseData((prev) => ({
                  ...prev,
                  sharpened: updated.sharpened,
                  not_investigating: updated.not_investigating,
                }));
                setToast({ message: "Case framing updated.", type: "success" });
              }}
            />
          )}
        </div>
      </div>

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onDismiss={() => setToast(null)}
        />
      )}
    </>
  );
}

function NotInvestigatingChip({ label }) {
  const [dismissed, setDismissed] = React.useState(false);
  if (dismissed) return null;
  return (
    <span
      className="src"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        textDecoration: "line-through",
      }}
    >
      {label}
      <button
        onClick={() => setDismissed(true)}
        aria-label={`Dismiss: ${label}`}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "0 2px",
          color: "var(--text-sub)",
          lineHeight: 1,
        }}
      >
        <i className="ti ti-x" style={{ fontSize: 10 }} aria-hidden="true"></i>
      </button>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Toast — transient success / error message
// ---------------------------------------------------------------------------

function Toast({ message, type, onDismiss }) {
  React.useEffect(() => {
    const t = setTimeout(onDismiss, 3500);
    return () => clearTimeout(t);
  }, [onDismiss]);
  const bg = type === "error" ? "var(--red-bg)" : "var(--green-bg)";
  const border = type === "error" ? "var(--red)" : "var(--green)";
  const color = type === "error" ? "var(--red)" : "var(--green)";
  const icon = type === "error" ? "ti-alert-circle" : "ti-check";
  return (
    <div
      role="alert"
      aria-live="polite"
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 200,
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: "var(--radius)",
        padding: "var(--space-3) var(--space-4)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-2)",
        boxShadow: "var(--shadow-hover)",
        maxWidth: 360,
      }}
    >
      <i
        className={`ti ${icon}`}
        aria-hidden="true"
        style={{ color, flexShrink: 0 }}
      ></i>
      <span style={{ fontSize: "var(--text-sm)", color, flex: 1 }}>
        {message}
      </span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color,
          padding: "0 2px",
          lineHeight: 1,
          flexShrink: 0,
        }}
      >
        <i className="ti ti-x" style={{ fontSize: 12 }} aria-hidden="true"></i>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EditCaseModal — inline modal for editing sharpened + not_investigating
// ---------------------------------------------------------------------------

function EditCaseModal({
  caseId,
  initialSharpened,
  initialNotInvestigating,
  onClose,
  onSaved,
}) {
  const [sharpened, setSharpened] = React.useState(initialSharpened || "");
  const [niText, setNiText] = React.useState(
    (initialNotInvestigating || []).join("\n"),
  );
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");

  const isDirty =
    sharpened !== (initialSharpened || "") ||
    niText !== (initialNotInvestigating || []).join("\n");

  React.useEffect(() => {
    function onKeyDown(e) {
      if (e.key === "Escape") {
        if (isDirty) {
          if (!window.confirm("Discard unsaved changes?")) return;
        }
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, isDirty]);

  function handleCancel() {
    if (isDirty && !window.confirm("Discard unsaved changes?")) return;
    onClose();
  }

  async function handleSave() {
    if (!sharpened.trim()) {
      setError("Sharpened statement must not be empty.");
      return;
    }
    const items = niText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    setSaving(true);
    setError("");
    try {
      const resp = await fetch(`/api/cases/${caseId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          sharpened: sharpened.trim(),
          not_investigating: items,
        }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || "An unexpected error occurred.");
      }
      const data = await resp.json();
      onSaved(data);
      onClose();
    } catch (err) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setSaving(false);
    }
  }

  const fieldStyle = {
    width: "100%",
    padding: "var(--space-3)",
    fontSize: "var(--text-base)",
    color: "var(--text)",
    background: "var(--surface-2)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    lineHeight: 1.55,
    boxSizing: "border-box",
  };

  return (
    <div
      onClick={handleCancel}
      role="dialog"
      aria-modal="true"
      aria-label="Edit case framing"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-5)",
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 560,
          maxWidth: "100%",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-card)",
          padding: "var(--space-6)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "var(--space-4)",
          }}
        >
          <h2
            style={{
              fontSize: "var(--text-xl)",
              fontWeight: 800,
              color: "var(--text)",
            }}
          >
            Edit case framing
          </h2>
          <button
            className="btn btn-sm"
            onClick={handleCancel}
            aria-label="Close"
            style={{ padding: "6px 8px" }}
          >
            <i className="ti ti-x" aria-hidden="true"></i>
          </button>
        </div>

        <div style={{ marginBottom: "var(--space-4)" }}>
          <label
            style={{
              display: "block",
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--text-muted)",
              fontFamily: "var(--font-mono)",
              textTransform: "uppercase",
              letterSpacing: ".05em",
              marginBottom: "var(--space-2)",
            }}
          >
            Sharpened statement <span style={{ color: "var(--red)" }}>*</span>
          </label>
          <textarea
            value={sharpened}
            onChange={(e) => {
              setSharpened(e.target.value);
              setError("");
            }}
            rows={4}
            disabled={saving}
            style={{
              ...fieldStyle,
              resize: "vertical",
              opacity: saving ? 0.6 : 1,
            }}
          />
        </div>

        <div style={{ marginBottom: "var(--space-5)" }}>
          <label
            style={{
              display: "block",
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--text-muted)",
              fontFamily: "var(--font-mono)",
              textTransform: "uppercase",
              letterSpacing: ".05em",
              marginBottom: "var(--space-1)",
            }}
          >
            Not investigating
          </label>
          <p
            style={{
              fontSize: "var(--text-xs)",
              color: "var(--text-sub)",
              margin: "0 0 var(--space-2)",
            }}
          >
            One item per line. Empty lines are ignored.
          </p>
          <textarea
            value={niText}
            onChange={(e) => setNiText(e.target.value)}
            rows={4}
            disabled={saving}
            placeholder="Enter items to exclude, one per line…"
            style={{
              ...fieldStyle,
              resize: "vertical",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-sm)",
              opacity: saving ? 0.6 : 1,
            }}
          />
        </div>

        {error && (
          <p
            role="alert"
            style={{
              color: "var(--red)",
              fontSize: "var(--text-sm)",
              marginBottom: "var(--space-3)",
            }}
          >
            {error}
          </p>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "var(--space-2)",
          }}
        >
          <button className="btn" onClick={handleCancel} disabled={saving}>
            Cancel
          </button>
          <button
            className="btn btn-crux"
            onClick={handleSave}
            disabled={saving}
            aria-busy={saving}
          >
            {saving ? (
              <>
                <i className="ti ti-loader-2 crux-spin" aria-hidden="true"></i>{" "}
                Saving…
              </>
            ) : (
              <>
                <i className="ti ti-check" aria-hidden="true"></i> Save changes
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CasesScreen
// ---------------------------------------------------------------------------

function CasesScreen({ theme, onToggleTheme, onCaseCreated }) {
  const [cases, setCases] = React.useState(null);
  const [showModal, setShowModal] = React.useState(false);

  // Search state: raw input value + debounced value applied to the filter
  const [searchQuery, setSearchQuery] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");

  // Filter state: Sets of active stage values (0-5) and active outcome chip labels
  const [activeStages, setActiveStages] = React.useState(new Set());
  const [activeOutcomes, setActiveOutcomes] = React.useState(new Set());

  // Stage and outcome chip definitions (kept inside the component so label strings
  // are part of the component's source for static inspection and future i18n)
  const STAGE_CHIP_DEFS = [
    { label: "Sharpened", value: 0 },
    { label: "Bake-off", value: 1 },
    { label: "Gather", value: 2 },
    { label: "Weigh", value: 3 },
    { label: "Probe", value: 4 },
    { label: "Verdict", value: 5 },
  ];

  const OUTCOME_CHIP_DEFS = [
    { label: "Open", values: ["awaiting", "progress"] },
    { label: "Confirmed", values: ["confirmed"] },
    { label: "Killed", values: ["killed"] },
    { label: "Inconclusive", values: ["inconclusive"] },
  ];

  React.useEffect(() => {
    fetch("/api/cases")
      .then((r) => r.json())
      .then((data) => setCases(data.cases))
      .catch(() => setCases([]));
  }, []);

  // 300ms debounce: update debouncedQuery after typing stops
  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  function toggleStage(value) {
    setActiveStages((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  function toggleOutcome(label) {
    setActiveOutcomes((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  function clearAll() {
    setSearchQuery("");
    setDebouncedQuery("");
    setActiveStages(new Set());
    setActiveOutcomes(new Set());
  }

  const hasActiveFilters =
    debouncedQuery.trim() !== "" ||
    activeStages.size > 0 ||
    activeOutcomes.size > 0;

  // Client-side filter — applies all active criteria with AND logic between groups
  const filteredCases = React.useMemo(() => {
    if (cases === null) return null;
    let list = cases;

    if (debouncedQuery.trim()) {
      const q = debouncedQuery.trim().toLowerCase();
      list = list.filter((c) => (c.title || "").toLowerCase().includes(q));
    }

    if (activeStages.size > 0) {
      list = list.filter((c) => activeStages.has(c.stage));
    }

    if (activeOutcomes.size > 0) {
      const verdictValues = new Set();
      OUTCOME_CHIP_DEFS.forEach((chip) => {
        if (activeOutcomes.has(chip.label))
          chip.values.forEach((v) => verdictValues.add(v));
      });
      list = list.filter((c) => verdictValues.has(c.verdict));
    }

    return list;
  }, [cases, debouncedQuery, activeStages, activeOutcomes]);

  if (cases === null) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
        }}
      >
        Loading…
      </div>
    );
  }

  const visibleCases = filteredCases || [];
  const open = visibleCases.filter(
    (c) => c.verdict === "progress" || c.verdict === "awaiting",
  );
  const closed = visibleCases.filter((c) => c.verdict_log);

  const _chipStyle = (active) => ({
    padding: "3px 12px",
    borderRadius: "var(--radius-pill)",
    border: `1px solid ${active ? "var(--crux)" : "var(--border)"}`,
    background: active ? "var(--crux-bg)" : "var(--surface-2)",
    color: active ? "var(--crux)" : "var(--text-muted)",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-xs)",
    fontWeight: 700,
    cursor: "pointer",
    transition: "all var(--speed)",
  });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Page header */}
      <header
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "var(--space-4)",
          padding: "var(--space-5) var(--space-6)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "var(--text-2xl)",
              fontWeight: 800,
              letterSpacing: "-.01em",
              color: "var(--text)",
            }}
          >
            Cases
          </h1>
          <p
            style={{
              fontSize: "var(--text-base)",
              color: "var(--text-muted)",
              marginTop: 4,
            }}
          >
            Open problems racing toward a verdict.
          </p>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
          }}
        >
          <button className="btn btn-crux" onClick={() => setShowModal(true)}>
            <i className="ti ti-plus" aria-hidden="true"></i> New case
          </button>
          <button
            className="btn btn-sm"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
            style={{ padding: "7px 9px" }}
          >
            <i
              className={`ti ti-${theme === "dark" ? "sun" : "moon"}`}
              aria-hidden="true"
            ></i>
          </button>
        </div>
      </header>

      {/* Search + filter bar */}
      <div
        style={{
          padding: "var(--space-3) var(--space-6)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-2)",
          background: "var(--surface)",
          flexShrink: 0,
        }}
      >
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search cases…"
          aria-label="Search cases"
          style={{
            padding: "var(--space-2) var(--space-3)",
            fontSize: "var(--text-base)",
            color: "var(--text)",
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            width: "100%",
            boxSizing: "border-box",
          }}
        />

        {/* Stage filter chips */}
        <div
          style={{
            display: "flex",
            gap: "var(--space-2)",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <span
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--text-sub)",
              flex: "none",
              width: 52,
            }}
          >
            STAGE
          </span>
          <button
            style={_chipStyle(activeStages.size === 0)}
            onClick={() => setActiveStages(new Set())}
            aria-pressed={activeStages.size === 0}
          >
            All
          </button>
          {STAGE_CHIP_DEFS.map((chip) => (
            <button
              key={chip.label}
              style={_chipStyle(activeStages.has(chip.value))}
              onClick={() => toggleStage(chip.value)}
              aria-pressed={activeStages.has(chip.value)}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {/* Outcome filter chips */}
        <div
          style={{
            display: "flex",
            gap: "var(--space-2)",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <span
            className="mono"
            style={{
              fontSize: "var(--text-2xs)",
              fontWeight: 700,
              color: "var(--text-sub)",
              flex: "none",
              width: 52,
            }}
          >
            OUTCOME
          </span>
          <button
            style={_chipStyle(activeOutcomes.size === 0)}
            onClick={() => setActiveOutcomes(new Set())}
            aria-pressed={activeOutcomes.size === 0}
          >
            All
          </button>
          {OUTCOME_CHIP_DEFS.map((chip) => (
            <button
              key={chip.label}
              style={_chipStyle(activeOutcomes.has(chip.label))}
              onClick={() => toggleOutcome(chip.label)}
              aria-pressed={activeOutcomes.has(chip.label)}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {/* Clear all — only visible when at least one filter is active */}
        {hasActiveFilters && (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              className="btn btn-sm"
              onClick={clearAll}
              style={{ fontSize: "var(--text-xs)" }}
            >
              <i className="ti ti-x" aria-hidden="true"></i> Clear all
            </button>
          </div>
        )}
      </div>

      {/* Case list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-6)" }}>
        {cases.length === 0 ? (
          /* No cases in DB at all */
          <div
            style={{
              textAlign: "center",
              padding: "var(--space-7) 0",
              color: "var(--text-muted)",
            }}
          >
            <div
              style={{
                fontSize: "var(--text-xl)",
                fontWeight: 600,
                color: "var(--text)",
                marginBottom: "var(--space-2)",
              }}
            >
              No cases yet
            </div>
            <p style={{ fontSize: "var(--text-base)", lineHeight: 1.55 }}>
              Got a problem worth solving? Start a case.
            </p>
          </div>
        ) : hasActiveFilters && visibleCases.length === 0 ? (
          /* Filters active but nothing matches */
          <div
            style={{
              textAlign: "center",
              padding: "var(--space-7) 0",
              color: "var(--text-muted)",
            }}
          >
            <div
              style={{
                fontSize: "var(--text-xl)",
                fontWeight: 600,
                color: "var(--text)",
                marginBottom: "var(--space-2)",
              }}
            >
              No cases match your search and filters
            </div>
            <p style={{ fontSize: "var(--text-base)", lineHeight: 1.55 }}>
              Try adjusting your search or clearing the filters.
            </p>
          </div>
        ) : (
          <>
            {open.length > 0 && (
              <>
                <div
                  className="mono"
                  style={{
                    fontSize: "var(--text-2xs)",
                    fontWeight: 700,
                    color: "var(--text-sub)",
                    marginBottom: "var(--space-3)",
                  }}
                >
                  OPEN · {open.length}
                </div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-3)",
                    marginBottom: "var(--space-6)",
                  }}
                >
                  {open.map((c) => (
                    <CaseCard
                      key={c.id}
                      {...c}
                      onClick={() => onCaseCreated && onCaseCreated(c.id)}
                    />
                  ))}
                </div>
              </>
            )}
            {closed.length > 0 && (
              <>
                <div
                  className="mono"
                  style={{
                    fontSize: "var(--text-2xs)",
                    fontWeight: 700,
                    color: "var(--text-sub)",
                    marginBottom: "var(--space-3)",
                  }}
                >
                  CLOSED · {closed.length}
                </div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-3)",
                  }}
                >
                  {closed.map((c) => (
                    <CaseCard
                      key={c.id}
                      {...c}
                      onClick={() => onCaseCreated && onCaseCreated(c.id)}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {showModal && (
        <NewCaseModal
          onClose={() => setShowModal(false)}
          onCaseCreated={(id) => {
            setShowModal(false);
            if (onCaseCreated) onCaseCreated(id);
          }}
        />
      )}
    </div>
  );
}
