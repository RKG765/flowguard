import { render, screen } from "@testing-library/react";
import { ShieldHalf } from "lucide-react";
import { Kpi } from "./Kpi";
import { Field, RULE_STATUS, RuleStatusBadge, SEVERITY, SeverityBadge } from "./primitives";

describe("status badges never rely on color alone", () => {
  it.each(Object.entries(RULE_STATUS))("rule status %s has a text label and an icon", (key, meta) => {
    const { container } = render(<RuleStatusBadge status={key} />);
    expect(screen.getByText(meta.label)).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });
  it.each(Object.entries(SEVERITY))("severity %s has a text label and an icon", (key, meta) => {
    const { container } = render(<SeverityBadge severity={key} />);
    expect(screen.getByText(meta.label)).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });
});

describe("form fields", () => {
  it("label, hint and error are wired for screen readers", () => {
    render(<Field label="Password" hint="At least 8" error="Too short" />);
    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const describedBy = input.getAttribute("aria-describedby")!;
    expect(document.getElementById(describedBy.split(" ").pop()!)).toHaveTextContent("Too short");
  });
});

describe("KPI card", () => {
  it("shows an honest empty text instead of a number when there is no data", () => {
    render(<Kpi label="Mean detect time" value={null} icon={ShieldHalf} empty="No alerts yet" />);
    expect(screen.getByText("No alerts yet")).toBeInTheDocument();
  });
  it("shows the value with an accessible label", () => {
    render(<Kpi label="Protected rules" value={3} icon={ShieldHalf} />);
    expect(screen.getByLabelText("Protected rules: 3")).toBeInTheDocument();
  });
});
