// The content and the authored icons behind the architecture map.
//
// This module holds no state and no layout. `ArchitectureMap.tsx` composes it,
// and keeping the tables here stops that component from growing past the point
// where its interaction logic is readable.
//
// Every string here describes the repository as it stands. A stage names the
// AWS services that carry it, and a trace names its exact component chain. No
// value on this page is invented, and none of it states a metric the platform
// does not measure.

export type EvidenceKey = "implemented" | "deployed" | "observed";
export type StageKey = "ingest" | "train" | "evaluate" | "register" | "serve" | "monitor";
export type ActiveStageKey = StageKey | "retrain";
export type TraceKey = "pipeline" | "signed-api" | "drift";

export interface Stage {
  key: ActiveStageKey;
  label: string;
  /** The AWS services that carry the stage. Kept short; the node shows it. */
  service: string;
  detail: string;
}

export interface EvidenceProof {
  label: string;
  value: string;
  detail: string;
}

export const STAGES: Stage[] = [
  {
    key: "ingest",
    label: "Ingest",
    service: "S3 · Lambda",
    detail: "Validate raw rows against the shared feature contract.",
  },
  {
    key: "train",
    label: "Train",
    service: "SageMaker",
    detail: "Build deterministic train, validation, test, and API fixtures.",
  },
  {
    key: "evaluate",
    label: "Evaluate",
    service: "Processing job",
    detail: "Compare test AUC with the approved champion before promotion.",
  },
  {
    key: "register",
    label: "Register",
    service: "Model Registry",
    detail: "Register the challenger only when it passes the promotion gate.",
  },
  {
    key: "serve",
    label: "Serve",
    service: "API GW · Lambda",
    detail: "Validate and sign inference requests before the endpoint call.",
  },
  {
    key: "monitor",
    label: "Monitor",
    service: "Drift Lambda",
    detail: "Score captured traffic against the training distribution.",
  },
];

export const RETRAIN: Stage = {
  key: "retrain",
  label: "Retrain",
  service: "EventBridge",
  detail: "Start another pipeline execution after a real drift violation.",
};

export const EVIDENCE: Record<EvidenceKey, { label: string; focus: string }> = {
  implemented: { label: "Implemented", focus: "source and tests" },
  deployed: { label: "Deployed", focus: "dev infrastructure" },
  observed: { label: "Observed", focus: "runtime signal" },
};

export const STAGE_EVIDENCE: Record<ActiveStageKey, Record<EvidenceKey, EvidenceProof>> = {
  ingest: {
    implemented: {
      label: "Source",
      value: "src/ingestion/validate_handler.py",
      detail: "The handler validates each raw row against the shared schema.",
    },
    deployed: {
      label: "Boundary",
      value: "S3 → EventBridge → SQS → validation Lambda",
      detail: "The ingestion stack owns delivery, retries, and dead-letter handling.",
    },
    observed: {
      label: "Signal",
      value: "Curated or quarantine object, plus the validation log",
      detail: "A run shows accepted rows, rejected rows, and each rejection reason.",
    },
  },
  train: {
    implemented: {
      label: "Source",
      value: "src/pipeline/pipeline.py",
      detail: "The definition connects preprocessing, training, evaluation, and registration.",
    },
    deployed: {
      label: "Boundary",
      value: "SageMaker Pipeline and its execution role",
      detail: "The training stack supplies the pipeline execution boundary.",
    },
    observed: {
      label: "Signal",
      value: "Pipeline execution and step artifacts",
      detail: "A run exposes step status, cached outputs, and model artifacts.",
    },
  },
  evaluate: {
    implemented: {
      label: "Source",
      value: "src/pipeline/evaluate.py",
      detail: "The step calculates held-out test AUC and compares the champion.",
    },
    deployed: {
      label: "Boundary",
      value: "Evaluation processor inside the training pipeline",
      detail: "The managed evaluation step runs before model registration.",
    },
    observed: {
      label: "Signal",
      value: "Evaluation report and champion comparison",
      detail: "The report records the test result and the promotion inputs.",
    },
  },
  register: {
    implemented: {
      label: "Source",
      value: "src/pipeline/pipeline.py",
      detail: "The pipeline registers a challenger only after the promotion gate passes.",
    },
    deployed: {
      label: "Boundary",
      value: "SageMaker Model Registry package group",
      detail: "The registry stack owns the package group and its boundary.",
    },
    observed: {
      label: "Signal",
      value: "Package state and promotion gate result",
      detail: "The package record shows the challenger that reached the registry.",
    },
  },
  serve: {
    implemented: {
      label: "Source",
      value: "src/serving/proxy_handler.py",
      detail: "The proxy validates the record and signs the endpoint request.",
    },
    deployed: {
      label: "Boundary",
      value: "API Gateway → proxy Lambda → SageMaker endpoint",
      detail: "The serving stack keeps AWS credentials behind the API boundary.",
    },
    observed: {
      label: "Signal",
      value: "Signed prediction response and structured event",
      detail: "A smoke request exercises the deployed inference path.",
    },
  },
  monitor: {
    implemented: {
      label: "Source",
      value: "src/monitoring/drift_handler.py",
      detail: "The handler scores a capture window and emits a violation event.",
    },
    deployed: {
      label: "Boundary",
      value: "Scheduled drift Lambda and the monitoring alarms",
      detail: "The monitoring stack owns evaluation cadence and alert resources.",
    },
    observed: {
      label: "Signal",
      value: "Capture window, PSI result, and violation event",
      detail: "Runtime evidence shows the score that can close the retraining loop.",
    },
  },
  retrain: {
    implemented: {
      label: "Source",
      value: "src/monitoring/retrain_handler.py",
      detail: "The handler filters drift events and starts a pipeline execution.",
    },
    deployed: {
      label: "Boundary",
      value: "EventBridge → retrain Lambda → SageMaker Pipeline",
      detail: "The monitoring stack owns the event route and the retrain function.",
    },
    observed: {
      label: "Signal",
      value: "Violation event and the pipeline execution it started",
      detail: "The execution record proves that a drift violation started retraining.",
    },
  },
};

export interface TracePath {
  label: string;
  detail: string;
  /** The exact component chain, one AWS component per hop. */
  chain: readonly string[];
  stages: readonly ActiveStageKey[];
  representativeStage: ActiveStageKey;
}

export const TRACE_PATHS: Record<TraceKey, TracePath> = {
  pipeline: {
    label: "Pipeline",
    detail: "Validated data moves through training, evaluation, and model registration.",
    chain: ["S3", "EventBridge", "SQS", "SageMaker Pipeline", "Model Registry"],
    stages: ["ingest", "train", "evaluate", "register"],
    representativeStage: "train",
  },
  "signed-api": {
    label: "Signed API",
    detail: "A SigV4-signed request passes the API boundary before the endpoint invocation.",
    chain: ["API Gateway", "Proxy Lambda", "SageMaker endpoint"],
    stages: ["serve"],
    representativeStage: "serve",
  },
  drift: {
    label: "Drift",
    detail: "Captured traffic is scored, and a violation starts another pipeline run.",
    chain: ["Capture S3", "Drift Lambda", "EventBridge", "Retrain Lambda", "Pipeline"],
    stages: ["monitor", "retrain", "train"],
    representativeStage: "monitor",
  },
};

export const STAGE_TRACE: Record<ActiveStageKey, TraceKey> = {
  ingest: "pipeline",
  train: "pipeline",
  evaluate: "pipeline",
  register: "pipeline",
  serve: "signed-api",
  monitor: "drift",
  retrain: "drift",
};

export function StageIcon({ stage }: { stage: ActiveStageKey }) {
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

/** One drawn mark per trace, in the same stroke weight as the stage icons. */
export function TraceIcon({ trace }: { trace: TraceKey }) {
  if (trace === "pipeline") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M6 24h36M34 16l8 8-8 8" />
        <path d="M14 32 6 24l8-8" />
      </svg>
    );
  }
  if (trace === "signed-api") {
    return (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M24 6 8 13v12c0 9 7 15 16 17 9-2 16-8 16-17V13L24 6Z" />
        <circle cx="24" cy="22" r="4" />
        <path d="M24 26v7" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <path d="M5 30l7-11 6 7 6-14 6 12 5-6" />
      <circle cx="34" cy="34" r="7" />
      <path d="m39 39 5 5" />
    </svg>
  );
}

export function EvidenceIcon({ evidence }: { evidence: EvidenceKey }) {
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
