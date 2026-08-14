import { afterEach, describe, expect, it, vi } from "vitest";

import { getResults, predict, subscribe } from "./api";
import { ApiError } from "./types";

function respondWith(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => body,
  } as Response);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the API client", () => {
  it("returns the parsed body", async () => {
    vi.stubGlobal("fetch", respondWith({ available: false }));

    await expect(getResults()).resolves.toEqual({ available: false });
  });

  it("posts the record as JSON", async () => {
    const fetchMock = respondWith({ churn_probability: 0.25, churn: false });
    vi.stubGlobal("fetch", fetchMock);

    await predict({ tenure: 1, Contract: "Month-to-month" });

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/predict");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ tenure: 1, Contract: "Month-to-month" });
  });

  it("raises the message the API reported", async () => {
    vi.stubGlobal("fetch", respondWith({ error: "too many predictions" }, 429));

    // The backend's own wording reaches the reader, so a rate limit does not
    // read as a generic failure.
    await expect(predict({})).rejects.toThrow(new ApiError("too many predictions", 429));
  });

  it("names the status when the body carries no message", async () => {
    vi.stubGlobal("fetch", respondWith("<html>gateway</html>", 502));

    await expect(subscribe("reader@example.com")).rejects.toThrow(/HTTP 502/);
  });

  it("reports an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed to fetch")));

    await expect(getResults()).rejects.toThrow(/unreachable/);
  });
});
