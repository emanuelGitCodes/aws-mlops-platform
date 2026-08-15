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

interface EvidenceProof {
  label: string;
  value: string;
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

const EVIDENCE: Record<EvidenceKey, { label: string; focus: string }> = {
  implemented: {
    label: "Implemented",
    focus: "source and tests",
  },
  deployed: {
    label: "Deployed",
    focus: "dev infrastructure boundary",
  },
  observed: {
    label: "Observed",
    focus: "runtime evidence",
  },
};

const STAGE_EVIDENCE: Record<
  ActiveStageKey,
  Record<EvidenceKey, EvidenceProof>
> = {
  ingest: {
    implemented: {
      label: "Source + unit test",
      value: "src/ingestion/validate_handler.py",
      detail: "The handler validates each raw row against the shared schema.",
    },
    deployed: {
      label: "Dev infrastructure boundary",
      value: "S3 → EventBridge → SQS → validation Lambda",
      detail: "The ingestion stack owns delivery, retries, and dead-letter handling.",
    },
    observed: {
      label: "Runtime signal",
      value: "Curated or quarantine object + validation log",
      detail: "A run shows accepted rows, rejected rows, and each rejection reason.",
    },
  },
  train: {
    implemented: {
      label: "Pipeline definition",
      value: "src/pipeline/pipeline.py",
      detail: "The definition connects preprocessing, training, evaluation, and registration.",
    },
    deployed: {
      label: "Dev infrastructure boundary",
      value: "SageMaker Pipeline + execution role",
      detail: "The training stack supplies the pipeline execution boundary.",
    },
    observed: {
      label: "Runtime signal",
      value: "Pipeline execution + step artifacts",
      detail: "A run exposes step status, cached outputs, and model artifacts.",
    },
  },
  evaluate: {
    implemented: {
      label: "Evaluation source",
      value: "src/pipeline/evaluate.py",
      detail: "The step calculates held-out test AUC and compares the champion.",
    },
    deployed: {
      label: "Dev infrastructure boundary",
      value: "Evaluation processor inside the training pipeline",
      detail: "The managed evaluation step runs before model registration.",
    },
    observed: {
      label: "Runtime signal",
      value: "Evaluation report + champion comparison",
      detail: "The report records the test result and promotion inputs.",
    },
  },
  register: {
    implemented: {
      label: "Promotion source",
      value: "src/pipeline/pipeline.py",
      detail: "The pipeline registers a challenger only after the promotion gate passes.",
    },
    deployed: {
      label: "Dev infrastructure boundary",
      value: "SageMaker Model Registry package group",
      detail: "The registry stack owns the package group and its boundary.",
    },
    observed: {
      label: "Runtime signal",
      value: "Package state + promotion gate result",
      detail: "The package record shows the challenger that reached the registry.",
    },
  },
  serve: {
    implemented: {
      label: "Proxy source",
      value: "src/serving/proxy_handler.py",
      detail: "The proxy validates the record and signs the endpoint request.",
    },
    deployed: {
      label: "Dev infrastructure boundary",
      value: "API Gateway → proxy Lambda → SageMaker endpoint",
      detail: "The serving stack keeps AWS credentials behind the API boundary.",
    },
    observed: {
      label: "Runtime signal",
      value: "Signed prediction response + structured event",
      detail: "A smoke request exercises the deployed inference path.",
    },
  },
  monitor: {
    implemented: {
      label: "Drift source",
      value: "src/monitoring/drift_handler.py",
      detail: "The handler scores a capture window and emits a violation event.",
    },
    deployed: {
      label: "Dev infrastructure boundary",
      value: "Scheduled drift Lambda + monitoring alarms",
      detail: "The monitoring stack owns evaluation cadence and alert resources.",
    },
    observed: {
      label: "Runtime signal",
      value: "Capture window + PSI result + violation event",
      detail: "Runtime evidence shows the score that can close the retraining loop.",
    },
  },
  retrain: {
    implemented: {
      label: "Retrain source",
      value: "src/monitoring/retrain_handler.py",
      detail: "The handler filters drift events and starts a pipeline execution.",
    },
    deployed: {
      label: "Dev infrastructure boundary",
      value: "EventBridge → retrain Lambda → SageMaker Pipeline",
      detail: "The monitoring stack owns the event route and retrain function.",
    },
    observed: {
      label: "Runtime signal",
      value: "Violation event → pipeline execution ARN",
      detail: "The execution record proves that a drift violation started retraining.",
    },
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
  const selectedEvidence = STAGE_EVIDENCE[activeStage][activeEvidence];
  const evidencePath =
    `M ${STAGE_POSITION[activeStage].x} ${STAGE_POSITION[activeStage].y} ` +
    `H 78 V ${EVIDENCE_POSITION[activeEvidence]} H 80`;

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
          <div className="stage-readout-copy">
            <p className="stage-summary">{selectedStage.detail}</p>
            <div
              className="evidence-proof"
              key={`${activeStage}-${activeEvidence}`}
            >
              <span>{selectedEvidence.label}</span>
              <strong>{selectedEvidence.value}</strong>
              <p>{selectedEvidence.detail}</p>
            </div>
          </div>
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

      <aside
        className="evidence-rail"
        aria-label={`Apply an evidence lens to ${selectedStage.label}`}
      >
        <div className="evidence-rail-line" aria-hidden="true"><span /></div>
        {(Object.keys(EVIDENCE) as EvidenceKey[]).map((key) => (
          <button
            className={`evidence-tab${activeEvidence === key ? " is-active" : ""}`}
            type="button"
            key={key}
            aria-pressed={activeEvidence === key}
            aria-label={`Inspect ${selectedStage.label} ${EVIDENCE[key].focus}`}
            onClick={() => setActiveEvidence(key)}
          >
            <EvidenceIcon evidence={key} />
            <span>{EVIDENCE[key].label}</span>
            <small>{selectedStage.label}: {EVIDENCE[key].focus}</small>
          </button>
        ))}
      </aside>
      <svg
        key={`${activeStage}-${activeEvidence}`}
        className="stage-evidence-link"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          className="signal-afterimage"
          d={evidencePath}
        />
        <path
          className="signal-live"
          d={evidencePath}
        />
        <path className="signal-pulse" d={evidencePath} />
      </svg>
    </div>
  );
}
