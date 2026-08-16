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

      <details>
        <summary>Read the full report</summary>
        <pre>{JSON.stringify(results.report, null, 2)}</pre>
      </details>
    </section>
  );
}
