import type { EvaluationReport, ModelSchema } from "../types";

/** Read the AUC out of the SageMaker evaluation report, when it is there. */
function readAuc(report: unknown): number | null {
  if (typeof report !== "object" || report === null) return null;
  const metrics = (report as Record<string, unknown>)["binary_classification_metrics"];
  if (typeof metrics !== "object" || metrics === null) return null;
  const auc = (metrics as Record<string, unknown>)["auc"];
  if (typeof auc !== "object" || auc === null) return null;
  const value = (auc as Record<string, unknown>)["value"];
  return typeof value === "number" ? value : null;
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
        <h3>Latest evaluation</h3>
        {/* The prefix is empty before the first pipeline run, and the read can
            fail on its own. The backend tells the two apart. */}
        <p>{results.error ?? "No evaluation report has been published yet."}</p>
      </section>
    );
  }

  const auc = readAuc(results.report);
  return (
    <section className="evidence-panel">
      <h3>Latest evaluation</h3>
      <dl>
        <dt>Test AUC</dt>
        <dd>{auc === null ? "not reported" : auc.toFixed(4)}</dd>
        <dt>Decision threshold</dt>
        <dd>{schema.decision_threshold}</dd>
        <dt>Published</dt>
        <dd>{results.generated_at ?? "unknown"}</dd>
      </dl>
      <details>
        <summary>Inspect full report</summary>
        <pre>{JSON.stringify(results.report, null, 2)}</pre>
      </details>
    </section>
  );
}
