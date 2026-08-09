import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ProgressTracker from "../components/ProgressTracker";
import LoginPage from "../pages/LoginPage";
import { auth } from "../lib/api";

describe("authentication and progress UI", () => {
  it("keeps access tokens in session storage only", () => {
    auth.setToken("signed-token");
    expect(auth.token()).toBe("signed-token");
    expect(localStorage.getItem("agent_eval_access_token")).toBeNull();
    auth.clear();
    expect(auth.token()).toBeNull();
  });

  it("switches from login to account registration", () => {
    render(<LoginPage onAuthenticated={() => undefined} />);
    expect(screen.queryByLabelText("EMAIL")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /register/i }));
    expect(screen.getByLabelText("EMAIL")).toBeRequired();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("clamps unsafe progress values", () => {
    const { rerender } = render(<ProgressTracker stage="running" percent={140} />);
    expect(screen.getByRole("status")).toHaveTextContent("RUNNING · 100%");
    rerender(<ProgressTracker stage="queued" percent={-10} />);
    expect(screen.getByRole("status")).toHaveTextContent("QUEUED · 0%");
  });
});
