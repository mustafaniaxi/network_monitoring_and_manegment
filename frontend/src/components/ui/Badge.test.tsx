import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SeverityBadge, StatusBadge } from "./Badge";

describe("status badges", () => {
  it("always pairs status colour with a text label", () => {
    render(<StatusBadge status="down" />);
    expect(screen.getByText("Offline")).toBeInTheDocument();
  });

  it("shows unmonitored devices distinctly", () => {
    render(<StatusBadge status="up" monitored={false} />);
    expect(screen.getByText("Not monitored")).toBeInTheDocument();
  });

  it("labels severities", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });
});
