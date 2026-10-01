import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, buildUrl, errorMessage, request, setToken } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe("buildUrl", () => {
  it("skips empty values and repeats arrays", () => {
    expect(
      buildUrl("/alerts", { status: ["active", "acknowledged"], device_id: undefined, q: "" }),
    ).toBe("/api/v1/alerts?status=active&status=acknowledged");
  });
});

describe("errorMessage", () => {
  it("flattens FastAPI validation errors", () => {
    const detail = [
      {
        loc: ["body", "ip_address"],
        msg: "Value error, must be a valid IPv4/IPv6 address or hostname",
      },
    ];
    expect(errorMessage(detail, "x")).toBe(
      "ip_address: must be a valid IPv4/IPv6 address or hostname",
    );
    expect(errorMessage("Not found", "x")).toBe("Not found");
    expect(errorMessage(undefined, "fallback")).toBe("fallback");
  });
});

describe("request", () => {
  it("sends the bearer token and parses JSON", async () => {
    setToken("abc");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(request<{ ok: boolean }>("/devices")).resolves.toEqual({ ok: true });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer abc");
  });

  it("raises ApiError with the server's message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "A device with this name already exists" }), {
          status: 409,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const error = await request("/devices", { body: {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe("A device with this name already exists");
  });
});
