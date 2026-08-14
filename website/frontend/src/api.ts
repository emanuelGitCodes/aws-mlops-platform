// The one place that calls the backend.
//
// Every request is same-origin. The dev server proxies `/api` to the backend
// container, and CloudFront routes `/api/*` to the same origin in the deployed
// shape, so no build carries a backend URL.

import { ApiError } from "./types";
import type {
  CustomerRecord,
  EvaluationReport,
  ModelSchema,
  Prediction,
  Subscription,
} from "./types";

/** Read the JSON body, and raise the API's own message on a failure status. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (cause) {
    // fetch rejects only when the request never reached the server.
    throw new ApiError("the website is unreachable", 0);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // A proxy error page is not JSON. Fall through to the status below.
  }

  if (!response.ok) {
    const message =
      body && typeof body === "object" && "error" in body
        ? String((body as { error: unknown }).error)
        : `the request failed with HTTP ${response.status}`;
    throw new ApiError(message, response.status);
  }
  return body as T;
}

export const getSchema = (): Promise<ModelSchema> => request<ModelSchema>("/api/schema");

export const getResults = (): Promise<EvaluationReport> =>
  request<EvaluationReport>("/api/results");

export const predict = (record: CustomerRecord): Promise<Prediction> =>
  request<Prediction>("/api/predict", {
    method: "POST",
    body: JSON.stringify(record),
  });

export const subscribe = (email: string): Promise<Subscription> =>
  request<Subscription>("/api/subscribe", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
