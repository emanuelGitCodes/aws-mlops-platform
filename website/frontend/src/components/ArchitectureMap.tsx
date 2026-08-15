import { useState } from "react";

type EvidenceKey = "implemented" | "deployed" | "observed";
type StageKey = "ingest" | "train" | "evaluate" | "register" | "serve" | "monitor";
type ActiveStageKey = StageKey | "retrain";
type TraceKey = "pipeline" | "signed-api" | "drift";

interface Stage {
  key: StageKey;
  label: string;
  detail: string;
}

const STAGES: Stage[] = [
  {
    key: "ingest",
    label: "Ingest",
    detail: "Validate raw rows against the shared feature contract.",
  },
  {
    key: "train",
    label: "Train",
    detail: "Create deterministic train, validation, test, and API fixtures.",
  },
  {
    key: "evaluate",
    label: "Evaluate",
    detail: "Compare test AUC with the approved champion before promotion.",
  },
  {
    key: "register",
    label: "Register",
    detail: "Register the challenger only when it passes the promotion gate.",
  },
  {
    key: "serve",
    label: "Serve",
    detail: "Validate and sign inference requests before the endpoint call.",
  },
  {
    key: "monitor",
    label: "Monitor",
    detail: "Score captured traffic against the training distribution.",
  },
];

const RETRAIN = {
  label: "Retrain",
  detail: "Start another pipeline execution after a real drift violation.",
};

const EVIDENCE: Record<EvidenceKey, { label: string; detail: string }> = {
  implemented: {
    label: "Implemented",
    detail: "Source, tests, and synthesized infrastructure define the behavior.",
  },
  deployed: {
    label: "Deployed",
    detail: "The project records dev-account delivery separately from repository state.",
  },
  observed: {
    label: "Observed",
    detail: "Runtime checks and observation windows supply behavioral evidence.",
  },
};

const TRACE_PATHS: Record<
  TraceKey,
  {
    label: string;
    detail: string;
    components: string;
    stages: readonly ActiveStageKey[];
    representativeStage: ActiveStageKey;
  }
> = {
  pipeline: {
    label: "Pipeline",
    detail: "Validated data moves through training, evaluation, and model registration.",
    components: "S3 → EventBridge and SQS → SageMaker Pipeline → Model Registry",
    stages: ["ingest", "train", "evaluate", "register"],
    representativeStage: "train",
  },
  "signed-api": {
    label: "Signed API",
    detail: "A signed request passes the API boundary before the endpoint invocation.",
    components: "API Gateway → Proxy Lambda → SageMaker endpoint",
    stages: ["serve"],
    representativeStage: "serve",
  },
  drift: {
    label: "Drift",
    detail: "Captured traffic is scored, and a violation starts another pipeline run.",
    components: "Capture S3 → Drift Lambda → EventBridge → Retrain Lambda → Pipeline",
    stages: ["monitor", "retrain", "train"],
    representativeStage: "monitor",
  },
};

const STAGE_TRACE: Record<ActiveStageKey, TraceKey> = {
  ingest: "pipeline",
  train: "pipeline",
  evaluate: "pipeline",
  register: "pipeline",
  serve: "signed-api",
  monitor: "drift",
  retrain: "drift",
};

const STAGE_POSITION: Record<ActiveStageKey, { x: number; y: number }> = {
  ingest: { x: 6.5, y: 31 },
  train: { x: 19.5, y: 31 },
  evaluate: { x: 32.5, y: 31 },
  register: { x: 45.5, y: 31 },
  serve: { x: 58.5, y: 31 },
  monitor: { x: 71.5, y: 31 },
  retrain: { x: 19.5, y: 58 },
};

const EVIDENCE_POSITION: Record<EvidenceKey, number> = {
  implemented: 16.666,
  deployed: 50,
  observed: 83.333,
};

function StageIcon({ stage }: { stage: StageKey | "retrain" }) {
  if (stage === "ingest") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M8 10h32L29 25v11l-10 4V25L8 10Z" />
        <path d="M14 16h20M17 21h14" />
      </svg>
    );
  }
  if (stage === "train") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="24" cy="9" r="3" />
        <circle cx="11" cy="24" r="3" />
        <circle cx="37" cy="24" r="3" />
        <circle cx="24" cy="39" r="3" />
        <path d="m24 12-11 10m13-10 9 10M14 26l8 11m12-11-8 11M14 24h20" />
      </svg>
    );
  }
  if (stage === "evaluate") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="21" cy="21" r="13" />
        <path d="m30 30 10 10M13 27l6-7 5 4 7-10" />
      </svg>
    );
  }
  if (stage === "register") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="m24 6 14 8-14 8-14-8 14-8Zm-14 8v17l14 9 14-9V14M24 22v18" />
        <path d="m15 19 14-8m-10 14 14-8" />
      </svg>
    );
  }
  if (stage === "serve") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="m24 7 14 8v17l-14 9-14-9V15l14-8Z" />
        <path d="m18 24 4 4 9-10" />
      </svg>
    );
  }
  if (stage === "monitor") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M6 35V11h36v24H6Z" />
        <path d="m10 29 7-10 7 7 7-12 7 10M18 41h12" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <path d="M37 19a14 14 0 1 0 0 11" />
      <path d="m32 12 6 7 4-8M11 29a14 14 0 0 0 2 4" />
    </svg>
  );
}

function EvidenceIcon({ evidence }: { evidence: EvidenceKey }) {
  if (evidence === "implemented") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="m24 6 14 8v19l-14 9-14-9V14l14-8Z" />
        <path d="M16 19h16M16 25h10M16 31h13" />
      </svg>
    );
  }
  if (evidence === "deployed") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="m24 7 14 8v17l-14 9-14-9V15l14-8Z" />
        <path d="m10 15 14 8 14-8M24 23v18" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <path d="M6 35V11h36v24H6Z" />
      <path d="m10 29 7-10 7 7 7-12 7 10M31 35l8 8" />
    </svg>
  );
}

export function ArchitectureMap() {
  const [activeStage, setActiveStage] = useState<ActiveStageKey>("train");
  const [activeEvidence, setActiveEvidence] = useState<EvidenceKey>("observed");
  const [activeTrace, setActiveTrace] = useState<TraceKey>("pipeline");
  const selectedStage =
    activeStage === "retrain"
      ? RETRAIN
      : (STAGES.find((stage) => stage.key === activeStage) ?? STAGES[0]!);
  const selectedTrace = TRACE_PATHS[activeTrace];

  function selectStage(stage: ActiveStageKey) {
    setActiveStage(stage);
    setActiveTrace(STAGE_TRACE[stage]);
  }

  function selectTrace(trace: TraceKey) {
    setActiveTrace(trace);
    setActiveStage(TRACE_PATHS[trace].representativeStage);
  }

  return (
    <div
      className={`system-frame stage-${activeStage} evidence-${activeEvidence} trace-${activeTrace}`}
    >
      <div className="architecture-field">
        <div className="route-map" aria-label="Model lifecycle">
          <svg className="route-lines" viewBox="0 0 1200 420" preserveAspectRatio="none" aria-hidden="true">
            <path className="route-base" d="M78 170H1095" />
            <path className="route-loop" d="M1095 205V350H270V205" />
            <path
              className={`route-active${activeTrace === "pipeline" ? " is-active" : ""}`}
              d="M78 170H690"
            />
            <path
              className={`route-active${activeTrace === "signed-api" ? " is-active" : ""}`}
              d="M820 170H965"
            />
            <path
              className={`route-active${activeTrace === "drift" ? " is-active" : ""}`}
              d="M894 170H1095V350H270V205"
            />
            <circle cx="78" cy="170" r="5" />
            <circle cx="282" cy="170" r="5" />
            <circle cx="486" cy="170" r="5" />
            <circle cx="690" cy="170" r="5" />
            <circle cx="894" cy="170" r="5" />
            <circle cx="1095" cy="170" r="5" />
          </svg>

          <div className="stage-row">
            {STAGES.map((stage) => (
              <button
                className={`stage-node${
                  selectedTrace.stages.includes(stage.key) ? " is-trace-active" : ""
                }${activeStage === stage.key ? " is-active" : ""}`}
                type="button"
                key={stage.key}
                aria-pressed={activeStage === stage.key}
                onClick={() => selectStage(stage.key)}
              >
                <StageIcon stage={stage.key} />
                <span>{stage.label}</span>
              </button>
            ))}
          </div>

          <button
            className={`retrain-node${
              selectedTrace.stages.includes("retrain") ? " is-trace-active" : ""
            }`}
            type="button"
            aria-pressed={activeStage === "retrain"}
            onClick={() => selectStage("retrain")}
          >
            <StageIcon stage="retrain" />
            <span>Retrain</span>
          </button>
        </div>

        <div className="stage-readout" aria-live="polite">
          <span className="readout-key">
            {selectedStage.label} → {EVIDENCE[activeEvidence].label}
          </span>
          <p>{selectedStage.detail}</p>
        </div>

        <ul className="trace-ledger" aria-label="Select a platform trace path">
          {(Object.keys(TRACE_PATHS) as TraceKey[]).map((trace) => (
            <li key={trace}>
              <button
                className={`trace-control${activeTrace === trace ? " is-active" : ""}`}
                type="button"
                aria-pressed={activeTrace === trace}
                onClick={() => selectTrace(trace)}
              >
                <span>{TRACE_PATHS[trace].label}</span>
                <i className="trace-track" aria-hidden="true"><b /></i>
              </button>
            </li>
          ))}
        </ul>

        <div className="trace-detail" aria-live="polite">
          <span>{selectedTrace.label} path</span>
          <p>{selectedTrace.detail}</p>
          <strong>{selectedTrace.components}</strong>
        </div>
      </div>

      <aside className="evidence-rail" aria-label="Evidence categories">
        <div className="evidence-rail-line" aria-hidden="true"><span /></div>
        {(Object.keys(EVIDENCE) as EvidenceKey[]).map((key) => (
          <button
            className={`evidence-tab${activeEvidence === key ? " is-active" : ""}`}
            type="button"
            key={key}
            aria-pressed={activeEvidence === key}
            onClick={() => setActiveEvidence(key)}
          >
            <EvidenceIcon evidence={key} />
            <span>{EVIDENCE[key].label}</span>
            <small>{EVIDENCE[key].detail}</small>
          </button>
        ))}
      </aside>
      <svg
        className="stage-evidence-link"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          className="signal-afterimage"
          d={`M ${STAGE_POSITION[activeStage].x} ${STAGE_POSITION[activeStage].y} H 78 V ${EVIDENCE_POSITION[activeEvidence]} H 80`}
        />
        <path
          className="signal-live"
          d={`M ${STAGE_POSITION[activeStage].x} ${STAGE_POSITION[activeStage].y} H 78 V ${EVIDENCE_POSITION[activeEvidence]} H 80`}
        />
      </svg>
    </div>
  );
}
