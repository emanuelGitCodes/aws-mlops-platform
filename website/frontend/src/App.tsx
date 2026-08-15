import { useEffect, useState } from "react";

import { getResults, getSchema } from "./api";
import { ArchitectureMap } from "./components/ArchitectureMap";
import { LatestEvaluation } from "./components/LatestEvaluation";
import { PredictForm } from "./components/PredictForm";
import { SchemaTable } from "./components/SchemaTable";
import { SubscribeForm } from "./components/SubscribeForm";
import { ApiError } from "./types";
import type { EvaluationReport, ModelSchema } from "./types";

export function App() {
  const [schema, setSchema] = useState<ModelSchema | null>(null);
  const [results, setResults] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The schema drives every other section, so a failure here is fatal to the
    // page. A failed report is not: that section reports its own state.
    getSchema()
      .then(setSchema)
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : "the model schema is unavailable"),
      );
    getResults()
      .then(setResults)
      .catch(() => setResults({ available: false, error: "the report is unavailable" }));
  }, []);

  return (
    <div className="site-shell">
      <main>
        <section className="terminal-shell" id="architecture" aria-labelledby="platform-title">
          <div className="terminal-heading">
            <div>
              <h1 id="platform-title">AWS MLOPS REFERENCE PLATFORM</h1>
              <p>
                Engineering the full model lifecycle so architecture,
                operational boundaries, and evidence stay inspectable.
              </p>
            </div>
          </div>

          <ArchitectureMap />

          <div className="terminal-actions">
            <a className="terminal-key terminal-key-primary" href="#system-notes">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M3 5h18v14H3V5Zm4 4h4m-4 4h8m-8 4h5" />
              </svg>
              Trace the platform
            </a>
            <a
              className="terminal-key"
              href="https://github.com/emanuelGitCodes/aws-mlops-platform"
              target="_blank"
              rel="noreferrer"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m8 7-5 5 5 5m8-10 5 5-5 5M14 4l-4 16" />
              </svg>
              GitHub source
            </a>
            <a className="terminal-key" href="#prediction-demo">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m5 7 5 5-5 5m8 0h6" />
              </svg>
              Try prediction
            </a>
          </div>
        </section>

        <section className="system-notes" id="system-notes" aria-labelledby="system-notes-title">
          <div className="section-heading">
            <h2 id="system-notes-title">The model is simple. The system is the work.</h2>
            <p>
              The repository separates data, training, registry, serving, monitoring,
              security, and delivery into distinct infrastructure boundaries.
            </p>
          </div>
          <div className="system-story">
            <article>
              <h3>Promotion has a gate</h3>
              <p>
                A challenger reaches the registry only when its held-out test AUC
                beats the approved champion.
              </p>
            </article>
            <article>
              <h3>Inference has a contract</h3>
              <p>
                One shared schema owns feature order and accepted values. The API
                validates each request before it reaches SageMaker.
              </p>
            </article>
            <article>
              <h3>Drift closes the loop</h3>
              <p>
                Captured inputs are compared with the training baseline. A real
                violation starts another pipeline execution.
              </p>
            </article>
          </div>
        </section>

        <section className="live-evidence" aria-labelledby="live-evidence-title">
          <div className="section-heading">
            <h2 id="live-evidence-title">Inspect the runtime contract.</h2>
            <p>
              These sections read the backend. They show the model contract and the
              latest evaluation without replacing architecture evidence with demo theater.
            </p>
          </div>

          {error && (
            <p className="status-message status-error" role="alert">
              <span>Connection fault</span>
              {error}. Start the local backend, then reload this page.
            </p>
          )}
          {!schema && !error && (
            <p className="status-message" aria-live="polite">
              <span>Reading contract</span>
              Loading the model schema and evaluation record…
            </p>
          )}

          {schema && (
            <div className="evidence-workbench">
              <SchemaTable schema={schema} />
              {results && <LatestEvaluation results={results} schema={schema} />}
            </div>
          )}
        </section>

        <section className="prediction-section" id="prediction-demo" aria-labelledby="prediction-title">
          <div className="section-heading">
            <h2 id="prediction-title">Run the secondary demo.</h2>
            <p>
              Submit one schema-driven record through the same backend contract.
              This demo supports the architecture; it is not the project claim.
            </p>
          </div>
          {schema ? (
            <PredictForm schema={schema} />
          ) : (
            <p className="status-message">The prediction form needs the model schema.</p>
          )}
        </section>

        <footer className="site-footer">
          <div>
            <strong>AWS MLOps reference platform</strong>
            <p>Built to make engineering decisions inspectable.</p>
          </div>
          <SubscribeForm />
        </footer>
      </main>
    </div>
  );
}
