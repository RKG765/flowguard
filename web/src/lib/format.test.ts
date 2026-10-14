import { renderHook } from "@testing-library/react";
import { csvCell, diffLines, formatInstructions, formatMatch, shortCookie } from "./format";
import { useWindow } from "./useWindow";
import { switchHealth } from "@/pages/Topology";
import type { RuleRow } from "./types";

describe("rule formatting", () => {
  it("matches read as field=value with hex ethertypes and masks", () => {
    expect(formatMatch({ eth_type: 2048, ip_proto: 6, tcp_dst: 23 })).toBe("eth_type=0x800, ip_proto=6, tcp_dst=23");
    expect(formatMatch({ ipv4_dst: ["10.0.0.0", "255.255.255.0"] })).toBe("ipv4_dst=10.0.0.0/255.255.255.0");
    expect(formatMatch({})).toBe("any packet");
  });
  it("instructions read in plain OpenFlow terms; no instructions means drop", () => {
    expect(formatInstructions([])).toEqual(["drop"]);
    expect(formatInstructions([{ type: "goto_table", table_id: 1 }])).toEqual(["goto_table:1"]);
    expect(formatInstructions([{ type: "apply_actions", actions: [{ type: "output", port: 1 }, { type: "output", port: 0xfffffffd, max_len: 65535 }] }]))
      .toEqual(["apply: output:1, output:CONTROLLER"]);
  });
  it("diff marks lines that exist on only one side", () => {
    expect(diffLines(["drop"], ["apply: output:1"])).toEqual([{ line: "drop", side: "signed" }, { line: "apply: output:1", side: "observed" }]);
    expect(diffLines(["goto_table:1"], ["goto_table:1"])).toEqual([{ line: "goto_table:1", side: "both" }]);
  });
  it("CSV cells are formula-safe and quoted", () => {
    expect(csvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(csvCell('a,"b"')).toBe('"a,""b"""');
    expect(csvCell(null)).toBe("");
  });
  it("cookies are shown without leading zeros", () => {
    expect(shortCookie("0003fdfe39c20001")).toBe("0x3fdfe39c20001");
    expect(shortCookie(null)).toBe("—");
  });
});

describe("windowed rows", () => {
  it("renders only what is visible plus overscan", () => {
    const { result } = renderHook(() => useWindow(10_000, 44, 520, 8));
    expect(result.current.first).toBe(0);
    expect(result.current.last).toBe(Math.ceil(520 / 44) + 8);
    expect(result.current.padBottom).toBe((10_000 - result.current.last) * 44);
  });
});

describe("switch health colour", () => {
  const row = (status: RuleRow["status"]): RuleRow => ({ dpid: "1", table_id: 0, priority: 1, match: {}, instructions: [], cookie: null, status,
    golden: true, golden_cookie: null, present: true, last_verified: 0 });
  it("uses the worst rule status", () => {
    expect(switchHealth([]).tone).toBe("muted");
    expect(switchHealth([row("ok"), row("ok")]).tone).toBe("ok");
    expect(switchHealth([row("ok"), row("pending")]).tone).toBe("info");
    expect(switchHealth([row("ok"), row("missing")]).tone).toBe("warn");
    expect(switchHealth([row("missing"), row("forged")]).tone).toBe("danger");
  });
});
