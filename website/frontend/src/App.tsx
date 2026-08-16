import { useEffect, useState } from "react";

import { getResults, getSchema } from "./api";
import { ArchitectureMap } from "./components/ArchitectureMap";
import { LatestEvaluation } from "./components/LatestEvaluation";
import { PredictForm } from "./components/PredictForm";
import { SchemaTable } from "./components/SchemaTable";
import { SiteFooter } from "./components/SiteFooter";
import { SiteHeader } from "./components/SiteHeader";
import { PROFILE } from "./profile";
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
    <div className="site-shell" id="top">
      <a className="skip-link" href="#architecture">
        Skip to the architecture
      </a>

      <SiteHeader />

      <main>
        <section className="terminal-shell" id="architecture" aria-labelledby="platform-title">
          <div className="terminal-heading">
            <h1 id="platform-title">AWS MLOps Reference Platform</h1>
            <p>
              Nine CDK stacks carrying one model. A promotion gate that can reject a
              challenger, an inference path where the browser never holds AWS
              credentials, and a drift check that starts its own retraining run.
            </p>
          </div>

          <ArchitectureMap />

          <div className="terminal-actions">
            <a
              className="terminal-key terminal-key-primary"
              href={PROFILE.repository}
              target="_blank"
              rel="noreferrer"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m8 7-5 5 5 5m8-10 5 5-5 5M14 4l-4 16" />
              </svg>
              Read the source
            </a>
            <a className="terminal-key" href="#approach">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M3 5h18v14H3V5Zm4 4h4m-4 4h8m-8 4h5" />
              </svg>
              How it was built
            </a>
            <a className="terminal-key" href="#demo">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m5 7 5 5-5 5m8 0h6" />
              </svg>
              Score a customer
            </a>
          </div>
        </section>

        <section className="approach" id="approach" aria-labelledby="approach-title">
          <div className="section-heading">
            <h2 id="approach-title">The model is simple. The system is the work.</h2>
            {/* Written in the first person on purpose. A reader who has seen
                fifty portfolio sites has not seen the engineer in any of them.
                EDIT THIS: it should sound like you, not like your README. */}
            <div className="approach-voice">
              <p>
                I built this to answer a question I kept fumbling in interviews: what
                does it actually take to run a model in production?
              </p>
              <p>
                The churn classifier is deliberately boring. Everything around it is the
                work — the pipeline that can refuse to promote a model, the signed
                boundary in front of inference, the drift check that reruns training
                without a person in the loop. It lives in a real AWS account on a $20
                monthly budget, and that budget shaped more decisions than any
                architecture diagram did.
              </p>
              <p>
                The thing I got wrong: I designed the infrastructure for this website
                before I designed the website, then had to stop and rebuild it in the
                right order. The stack stays written and tested, and it ships after the
                application it carries runs.
              </p>
              <p className="voice-record">
                Every phase carries a written record — the decision, the deploy, the
                observation window, and the go or no-go call.{" "}
                <a href={`${PROFILE.repository}/tree/main/wiki`} target="_blank" rel="noreferrer">
                  Read the engineering wiki
                </a>
                .
              </p>
            </div>
          </div>

          <div className="system-story">
            <article>
              <h3>Promotion has a gate</h3>
              <p>
                A challenger reaches the registry only when its held-out test AUC beats
                the approved champion. A worse model stops at the gate.
              </p>
            </article>
            <article>
              <h3>Inference has a contract</h3>
              <p>
                One shared module owns feature order and accepted values. The API
                validates every request against it before SageMaker sees the record.
              </p>
            </article>
            <article>
              <h3>Drift closes the loop</h3>
              <p>
                Captured inputs are scored against the training baseline. A real
                violation starts another pipeline execution on its own.
              </p>
            </article>
            <article>
              <h3>The blast radius is code</h3>
              <p>
                The deployment role's permissions live in this repository, version
                pinned and fingerprint tested. Widening them takes a reviewed commit.
              </p>
            </article>
          </div>
        </section>

        <section className="live-evidence" id="contract" aria-labelledby="contract-title">
          <div className="section-heading">
            <h2 id="contract-title">Read the running contract.</h2>
            <p>
              Both panels below are fetched from the backend when this page loads.
              Nothing here is typed into the markup.
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
              <span>Reading</span>
              Loading the model contract and the newest evaluation…
            </p>
          )}

          {schema && (
            <div className="evidence-workbench">
              <SchemaTable schema={schema} />
              {results && <LatestEvaluation results={results} schema={schema} />}
            </div>
          )}
        </section>

        <section className="prediction-section" id="demo" aria-labelledby="demo-title">
          <div className="section-heading">
            <h2 id="demo-title">Score a customer.</h2>
            <p>
              One record, through the same validation and the same signed path the
              platform uses. Load an example or change any field.
            </p>
          </div>
          {schema ? (
            <PredictForm schema={schema} />
          ) : (
            <p className="status-message">The form needs the model contract.</p>
          )}
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
