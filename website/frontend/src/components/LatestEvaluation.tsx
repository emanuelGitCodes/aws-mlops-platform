import type { EvaluationReport, ModelSchema } from "../types";

/**
 * Read the AUC out of the newest evaluation report, when it is there.
 *
 * The pipeline writes two reports per execution. `evaluation.json` nests the
 * value in the SageMaker ModelMetrics shape, and `metrics.json` holds it as a
 * plain number beside the other metrics. Either one can be the newest object.
 */
function readAuc(report: unknown): number | null {
  if (typeof report !== "object" || report === null) return null;
  const fields = report as Record<string, unknown>;
  if (typeof fields["auc"] === "number") return fields["auc"];
  const metrics = fields["binary_classification_metrics"];
  if (typeof metrics !== "object" || metrics === null) return null;
  const auc = (metrics as Record<string, unknown>)["auc"];
  if (typeof auc !== "object" || auc === null) return null;
  const value = (auc as Record<string, unknown>)["value"];
  return typeof value === "number" ? value : null;
}

/** The rate metrics the panel charts, in the order it reads them. */
const RATE_METRICS: [label: string, key: string][] = [
  ["Accuracy", "accuracy"],
  ["Precision", "precision"],
  ["Recall", "recall"],
  ["F1", "f1"],
  ["Specificity", "specificity"],
];

/** The confusion matrix cells, as [row, column, key]. */
const MATRIX_CELLS: [row: 0 | 1, column: 0 | 1, key: string][] = [
  [0, 0, "true_negative"],
  [0, 1, "false_positive"],
  [1, 0, "false_negative"],
  [1, 1, "true_positive"],
];

function readNumbers(source: unknown, keys: string[]): Map<string, number> {
  const found = new Map<string, number>();
  if (typeof source !== "object" || source === null) return found;
  const fields = source as Record<string, unknown>;
  for (const key of keys) {
    const value = fields[key];
    if (typeof value === "number" && Number.isFinite(value)) found.set(key, value);
  }
  return found;
}

/**
 * Render an ISO timestamp as a date a person reads.
 *
 * S3 returns microsecond precision. That resolution says nothing to a reader,
 * and the raw string is the longest value in the panel.
 */
function readableDate(value: string | undefined): string {
  if (!value) return "unknown";
  const moment = new Date(value);
  if (Number.isNaN(moment.getTime())) return value;
  return moment.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function LatestEvaluation({
  results,
  schema,
}: {
  results: EvaluationReport;
  schema: ModelSchema;
}) {
  if (!results.available) {
    return (
      <section className="evidence-panel">
        <h3>Newest evaluation</h3>
        {/* The prefix is empty before the first pipeline run, and the read can
            fail on its own. The backend tells the two apart. */}
        <p>{results.error ?? "No evaluation report has been published yet."}</p>
      </section>
    );
  }

  const auc = readAuc(results.report);
  // `evaluation.json` carries the AUC alone. The rest of the panel appears
  // only when the newest object is the fuller `metrics.json` report.
  const rates = readNumbers(
    results.report,
    RATE_METRICS.map(([, key]) => key),
  );
  const counts = readNumbers(results.report, ["sample_count", "positive_count", "champion_test_auc"]);
  const decision = (results.report as Record<string, unknown> | null)?.["promotion_decision"];
  const matrix = readNumbers(
    (results.report as Record<string, unknown> | null)?.["confusion_matrix"],
    MATRIX_CELLS.map(([, , key]) => key),
  );
  return (
    <section className="evidence-panel">
      <h3>Newest evaluation</h3>
      <p>
        The pipeline writes this report, and the promotion gate reads it. A challenger
        reaches the registry only when it beats the approved champion on held-out test
        data.
      </p>

      <p className="headline-metric">
        <span className="metric-value">{auc === null ? "—" : auc.toFixed(4)}</span>
        <span className="metric-name">Test AUC</span>
      </p>

      {typeof decision === "string" && counts.has("champion_test_auc") && (
        <p className="gate-verdict">
          <span className={decision === "register" ? "gate-pass" : "gate-stop"}>
            {decision === "register" ? "Promoted" : "Rejected"}
          </span>
          {/* The pipeline passes 0.5 when the registry holds no approved package,
              so the run is a first model rather than a challenger. */}
          {counts.get("champion_test_auc") === 0.5
            ? "against the 0.5 baseline the gate uses with no approved champion"
            : `against a champion at ${(counts.get("champion_test_auc") as number).toFixed(4)}`}
        </p>
      )}

      <dl>
        <dt>Decision threshold</dt>
        <dd>{schema.decision_threshold}</dd>
        <dt>Published</dt>
        <dd>{readableDate(results.generated_at)}</dd>
        {results.key && (
          <>
            <dt>Report object</dt>
            <dd className="wraps">
              <code>{results.key}</code>
            </dd>
          </>
        )}
      </dl>

      {rates.size > 0 && (
        <div className="metric-bars">
          {RATE_METRICS.filter(([, key]) => rates.has(key)).map(([label, key]) => {
            const value = rates.get(key) as number;
            return (
              <p className="metric-bar" key={key}>
                <span className="bar-name">{label}</span>
                <span className="bar-value">{value.toFixed(3)}</span>
                {/* The number carries the value. The track repeats it. */}
                <span className="bar-track" aria-hidden="true">
                  <span className="bar-fill" style={{ width: `${value * 100}%` }} />
                </span>
              </p>
            );
          })}
          <p className="metric-note">
            Every rate above reads the {schema.decision_threshold} serving threshold. A
            lower threshold catches more churn and calls more loyal customers wrong. The
            endpoint returns the probability, so a caller picks the trade for its own
            campaign.
          </p>
        </div>
      )}

      {matrix.size === MATRIX_CELLS.length && (
        <table className="matrix">
          <caption>
            Confusion matrix at the decision threshold
            {counts.has("sample_count") && ` · ${counts.get("sample_count")} test records`}
            {counts.has("positive_count") && ` · ${counts.get("positive_count")} churned`}
          </caption>
          <thead>
            <tr>
              <td />
              <th scope="col">Said stay</th>
              <th scope="col">Said churn</th>
            </tr>
          </thead>
          <tbody>
            {(["Stayed", "Churned"] as const).map((rowName, row) => (
              <tr key={rowName}>
                <th scope="row">{rowName}</th>
                {MATRIX_CELLS.filter(([cellRow]) => cellRow === row).map(([, , key]) => (
                  <td key={key} className={key === "true_negative" || key === "true_positive" ? "hit" : undefined}>
                    {matrix.get(key)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <details>
        <summary>Read the full report</summary>
        <pre>{JSON.stringify(results.report, null, 2)}</pre>
      </details>
    </section>
  );
}
