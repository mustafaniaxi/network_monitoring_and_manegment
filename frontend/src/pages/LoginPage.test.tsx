import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/auth/AuthContext";
import { LoginPage } from "./LoginPage";

function renderLogin() {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/", element: <p>Dashboard home</p> },
    ],
    { initialEntries: ["/login"] },
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("LoginPage", () => {
  it("signs in and redirects to the dashboard", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      json({
        access_token: "token-1",
        token_type: "bearer",
        expires_in: 3600,
        user: {
          id: 1,
          email: "admin@netmon.local",
          full_name: "Admin",
          role: "admin",
          is_active: true,
          created_at: "",
          last_login_at: null,
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "admin@netmon.local");
    await userEvent.type(screen.getByLabelText("Password"), "secret-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Dashboard home")).toBeInTheDocument();
    expect(localStorage.getItem("netmon.token")).toBe("token-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/auth/login");
    expect(String(init.body)).toContain("username=admin%40netmon.local");
  });

  it("shows the server error on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ detail: "Incorrect email or password" }, 401)),
    );
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
  });
});
