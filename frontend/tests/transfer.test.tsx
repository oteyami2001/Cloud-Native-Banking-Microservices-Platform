import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../src/App";
import { AuthProvider, homeFor } from "../src/lib/auth";
import { validateTransfer } from "../src/pages/Transfer";

const A = "ACC-0000000000000000000A";
const B = "ACC-0000000000000000000B";

describe("validateTransfer", () => {
  it("accepts a valid transfer", () => {
    expect(validateTransfer(A, B, "250.00")).toEqual({ minor: 25000 });
  });
  it.each([
    ["", B, "1", "Choose a source account"],
    [A, "not-an-account", "1", "Destination must be a NovaBank account ID (ACC-…)"],
    [A, A, "1", "Source and destination must be different"],
    [A, B, "-5", "Enter a positive amount with at most two decimals"],
    [A, B, "1.999", "Enter a positive amount with at most two decimals"],
  ])("rejects %s → %s (%s)", (s, d, amt, msg) => {
    expect(validateTransfer(s, d, amt)).toEqual({ error: msg });
  });
});

describe("App", () => {
  it("shows the synthetic sandbox banner and protects customer pages", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole("note")).toHaveTextContent(/synthetic/i);
    // Unauthenticated users are sent to the login page; its wording depends on
    // the build's auth mode (offline personas locally, Cognito when deployed).
    expect(screen.getByRole("heading", { name: /Choose a sandbox persona|^Sign in$/ })).toBeInTheDocument();
  });
});

describe("homeFor", () => {
  it("sends each role to its own landing page", () => {
    expect(homeFor(["customers"])).toBe("/dashboard");
    expect(homeFor(["fraud-reviewers"])).toBe("/admin/fraud");
    expect(homeFor(["auditors"])).toBe("/admin/reconciliation");
    expect(homeFor([])).toBe("/");
  });
});
