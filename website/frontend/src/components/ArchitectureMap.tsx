import { useState } from "react";

import type { ActiveStageKey, EvidenceKey, TraceKey } from "./architecture-content";
import {
  EVIDENCE,
  EvidenceIcon,
  RETRAIN,
  STAGES,
  STAGE_EVIDENCE,
  STAGE_TRACE,
  StageIcon,
  TRACE_PATHS,
  TraceIcon,
} from "./architecture-content";
import type { Box } from "./useNodeBoxes";
import { bottomOf, leftOf, rightOf, topOf, useNodeBoxes } from "./useNodeBoxes";

type NodeKey = ActiveStageKey | `evidence-${EvidenceKey}`;

/** The gap a route leaves before a node, so the arrowhead sits clear of it. */
const ARROW_GAP = 5;

/** Draw the route from one node to the next, in whichever way they sit. */
function connector(from: Box, to: Box): string {
  if (to.x >= from.x + from.width - 1) {
    const start = rightOf(from);
    const end = leftOf(to);
    return `M ${start.x} ${start.y} H ${end.x - ARROW_GAP}`;
  }
  const start = bottomOf(from);
  const end = topOf(to);
  return `M ${start.x} ${start.y} V ${end.y - ARROW_GAP}`;
}

/**
 * Read the port marks a route meets.
 *
 * The comp lands every route on a small circle at the node's edge. The mark is
 * what makes a line read as connected to the box rather than as a line ending
 * near it, so each segment contributes the port it leaves from.
 */
function portsFor(from: Box, to: Box): { x: number; y: number }[] {
  if (to.x >= from.x + from.width - 1) return [rightOf(from), leftOf(to)];
  return [bottomOf(from), topOf(to)];
}

/**
 * Route the drift return from monitor to retrain.
 *
 * The path drops below the stage row, runs back along a clear lane, and enters
 * the retrain node from its right edge. The lane sits halfway between the two
 * rows, so it never crosses a node.
 */
function returnPath(monitor: Box, retrain: Box): string {
  const start = bottomOf(monitor);
  const end = rightOf(retrain);
  // Nothing sits below the last stage, so the path drops straight to the
  // retrain node's own line and enters it travelling left. A lane between the
  // two rows would run within a few pixels of the row above it.
  return `M ${start.x} ${start.y} V ${end.y} H ${end.x + ARROW_GAP}`;
}

/** Route the retrain trigger straight up into the stage it restarts. */
function triggerPath(retrain: Box, train: Box): string {
  const start = topOf(retrain);
  return `M ${start.x} ${start.y} V ${train.y + train.height + ARROW_GAP}`;
}

/**
 * Route the retrain trigger back up a side lane.
 *
 * When the stages stack into one column, the node the loop restarts is several
 * nodes above it. A straight vertical line would run through every node in
 * between, so the path leaves sideways and climbs beside the column.
 */
function loopBackPath(retrain: Box, train: Box, lane: number): string {
  const start = leftOf(retrain);
  const end = leftOf(train);
  return `M ${start.x} ${start.y} H ${lane} V ${end.y} H ${end.x - ARROW_GAP}`;
}

/**
 * Couple the selected stage to its proof lens across the frame.
 *
 * A stage in the lifecycle row sends its signal up and over the row, because a
 * line leaving its right edge would cut through every stage after it. The
 * retrain node has clear space beside it and goes straight out.
 */
function evidencePath(stage: Box, tab: Box, topLane: number, inRow: boolean): string {
  const end = leftOf(tab);
  const lane = end.x - 12;
  if (!inRow) {
    const start = rightOf(stage);
    return `M ${start.x} ${start.y} H ${lane} V ${end.y} H ${end.x}`;
  }
  const start = topOf(stage);
  return `M ${start.x} ${start.y} V ${topLane} H ${lane} V ${end.y} H ${end.x}`;
}

export function ArchitectureMap() {
  const [activeStage, setActiveStage] = useState<ActiveStageKey>("train");
  const [activeEvidence, setActiveEvidence] = useState<EvidenceKey>("observed");
  const [activeTrace, setActiveTrace] = useState<TraceKey>("pipeline");
  const { containerRef, registerNode, geometry } = useNodeBoxes<NodeKey>();

  const selectedStage =
    activeStage === "retrain" ? RETRAIN : (STAGES.find((s) => s.key === activeStage) ?? STAGES[0]!);
  const selectedTrace = TRACE_PATHS[activeTrace];
  const selectedEvidence = STAGE_EVIDENCE[activeStage][activeEvidence];
  const { boxes, width, height } = geometry;

  function selectStage(stage: ActiveStageKey) {
    setActiveStage(stage);
    setActiveTrace(STAGE_TRACE[stage]);
  }

  function selectTrace(trace: TraceKey) {
    setActiveTrace(trace);
    setActiveStage(TRACE_PATHS[trace].representativeStage);
  }

  // Each consecutive pair of stages, plus the two halves of the retrain loop.
  const segments: { key: string; d: string; stages: [ActiveStageKey, ActiveStageKey] }[] = [];
  const ports: { x: number; y: number }[] = [];
  for (let index = 0; index < STAGES.length - 1; index += 1) {
    const from = boxes[STAGES[index]!.key];
    const to = boxes[STAGES[index + 1]!.key];
    if (from && to) {
      segments.push({
        key: `${STAGES[index]!.key}-${STAGES[index + 1]!.key}`,
        d: connector(from, to),
        stages: [STAGES[index]!.key, STAGES[index + 1]!.key],
      });
      ports.push(...portsFor(from, to));
    }
  }
  const monitor = boxes.monitor;
  const retrain = boxes.retrain;
  const train = boxes.train;
  // Below the stacking breakpoint every node shares one column, so the retrain
  // node sits under the last stage instead of beside the one it restarts.
  const stacked = !!monitor && !!retrain && Math.abs(retrain.x - monitor.x) < 4;
  const lane =
    Math.min(...STAGES.map((s) => boxes[s.key]?.x ?? Infinity), retrain?.x ?? Infinity) - 8;

  if (monitor && retrain) {
    segments.push({
      key: "monitor-retrain",
      d: stacked ? connector(monitor, retrain) : returnPath(monitor, retrain),
      stages: ["monitor", "retrain"],
    });
    ports.push(
      ...(stacked ? portsFor(monitor, retrain) : [bottomOf(monitor), rightOf(retrain)]),
    );
  }
  if (retrain && train) {
    segments.push({
      key: "retrain-train",
      d: stacked
        ? loopBackPath(retrain, train, Math.max(lane, 3))
        : triggerPath(retrain, train),
      stages: ["retrain", "train"],
    });
    ports.push(stacked ? leftOf(retrain) : topOf(retrain), stacked ? leftOf(train) : bottomOf(train));
  }

  const stageBox = boxes[activeStage];
  const tabBox = boxes[`evidence-${activeEvidence}`];
  // The rail sits beside the field on wide screens and below it when stacked.
  // The coupling line only reads as a connection in the side-by-side case.
  const coupled = stageBox && tabBox && tabBox.x > stageBox.x + stageBox.width;
  const rowTop = boxes.ingest?.y ?? 0;
  const link = coupled
    ? evidencePath(stageBox, tabBox, Math.max(rowTop - 14, 4), activeStage !== "retrain")
    : null;

  return (
    <div
      className={`system-frame stage-${activeStage} evidence-${activeEvidence} trace-${activeTrace}`}
      ref={containerRef}
    >
      {width > 0 && (
        <svg
          className="route-layer"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          aria-hidden="true"
        >
          <defs>
            <marker
              id="route-arrow"
              markerWidth="7"
              markerHeight="7"
              refX="6"
              refY="3.5"
              orient="auto"
            >
              <path className="arrow-head" d="M0 0.5 6 3.5 0 6.5Z" />
            </marker>
            <marker
              id="route-arrow-live"
              markerWidth="7"
              markerHeight="7"
              refX="6"
              refY="3.5"
              orient="auto"
            >
              <path className="arrow-head is-live" d="M0 0.5 6 3.5 0 6.5Z" />
            </marker>
          </defs>

          {segments.map((segment) => {
            const live =
              selectedTrace.stages.includes(segment.stages[0]) &&
              selectedTrace.stages.includes(segment.stages[1]);
            return (
              <path
                key={segment.key}
                className={`route-edge${live ? " is-live" : ""}`}
                d={segment.d}
                markerEnd={`url(#${live ? "route-arrow-live" : "route-arrow"})`}
              />
            );
          })}

          {ports.map((port, index) => (
            <circle className="route-port" key={`${port.x}-${port.y}-${index}`} cx={port.x} cy={port.y} r="2.6" />
          ))}

          {link && tabBox && (
            <g key={`${activeStage}-${activeEvidence}`}>
              <path className="evidence-halo" d={link} />
              <path className="evidence-line" d={link} />
              <path className="evidence-pulse" d={link} />
              {/* The cursor lands on the rail as a lit node. It is the one
                  mark that says which proof lens the stage resolved to. */}
              <circle className="evidence-node-glow" cx={tabBox.x} cy={tabBox.y + tabBox.height / 2} r="9" />
              <circle className="evidence-node" cx={tabBox.x} cy={tabBox.y + tabBox.height / 2} r="4" />
            </g>
          )}
        </svg>
      )}

      <div className="architecture-field">
        <div className="stage-row">
          {STAGES.map((stage) => (
            <button
              className={`stage-node${
                selectedTrace.stages.includes(stage.key) ? " is-trace-active" : ""
              }${activeStage === stage.key ? " is-active" : ""}`}
              type="button"
              key={stage.key}
              ref={registerNode(stage.key)}
              aria-pressed={activeStage === stage.key}
              onClick={() => selectStage(stage.key)}
            >
              <StageIcon stage={stage.key} />
              <span className="stage-name">{stage.label}</span>
              <span className="stage-service">{stage.service}</span>
            </button>
          ))}
        </div>

        <div className="retrain-row">
          <button
            className={`stage-node retrain-node${
              selectedTrace.stages.includes("retrain") ? " is-trace-active" : ""
            }${activeStage === "retrain" ? " is-active" : ""}`}
            type="button"
            ref={registerNode("retrain")}
            aria-pressed={activeStage === "retrain"}
            onClick={() => selectStage("retrain")}
          >
            <StageIcon stage="retrain" />
            <span className="stage-name">{RETRAIN.label}</span>
            <span className="stage-service">{RETRAIN.service}</span>
          </button>
        </div>

        <div className="stage-readout" aria-live="polite">
          <p className="readout-key">
            {selectedStage.label} → {EVIDENCE[activeEvidence].label}
          </p>
          <div className="stage-readout-copy">
            <p className="stage-summary">{selectedStage.detail}</p>
            <div className="evidence-proof" key={`${activeStage}-${activeEvidence}`}>
              <span>{selectedEvidence.label}</span>
              <strong>{selectedEvidence.value}</strong>
              <p>{selectedEvidence.detail}</p>
            </div>
          </div>
        </div>

        <div className="trace-ledger">
          <ul aria-label="Select a platform trace path">
            {(Object.keys(TRACE_PATHS) as TraceKey[]).map((trace) => (
              <li key={trace}>
                <button
                  className={`trace-control${activeTrace === trace ? " is-active" : ""}`}
                  type="button"
                  aria-pressed={activeTrace === trace}
                  onClick={() => selectTrace(trace)}
                >
                  <span className="trace-name">
                    <TraceIcon trace={trace} />
                    {TRACE_PATHS[trace].label}
                  </span>
                  <span className="trace-chain">
                    {TRACE_PATHS[trace].chain.map((hop) => (
                      <span className="trace-hop" key={hop}>
                        {hop}
                      </span>
                    ))}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="trace-detail" aria-live="polite">
            {selectedTrace.detail}
          </p>
        </div>
      </div>

      <div className="evidence-rail" role="group" aria-label={`Proof lens for ${selectedStage.label}`}>
        {(Object.keys(EVIDENCE) as EvidenceKey[]).map((key) => (
          <button
            className={`evidence-tab${activeEvidence === key ? " is-active" : ""}`}
            type="button"
            key={key}
            ref={registerNode(`evidence-${key}`)}
            aria-pressed={activeEvidence === key}
            aria-label={`Show ${selectedStage.label} ${EVIDENCE[key].focus}`}
            onClick={() => setActiveEvidence(key)}
          >
            <span className="evidence-ring">
              <EvidenceIcon evidence={key} />
            </span>
            <span>{EVIDENCE[key].label}</span>
            <small>{EVIDENCE[key].focus}</small>
          </button>
        ))}
      </div>
    </div>
  );
}
