import { diffLines, formatInstructions, shortCookie, type Instruction } from "@/lib/format";
import { cn } from "@/lib/cn";
import { DataSurface } from "@/components/ui/primitives";
import { TagStripe } from "@/components/ui/Patch";

/** Signed (golden) vs what the switch actually holds. Lines only in one side are marked with text, not color alone. */
export function RuleDiff({ signed, observed, signedCookie, observedCookie, present = true }: {
  signed: Instruction[] | null | undefined;
  observed: Instruction[] | null | undefined;
  signedCookie?: string | null;
  observedCookie?: string | null;
  present?: boolean;
}) {
  const s = signed === null || signed === undefined ? null : formatInstructions(signed);
  const o = present ? formatInstructions(observed) : null;
  const rows = s && o ? diffLines(s, o) : null;
  return (
    <DataSurface className="grid grid-cols-2 divide-x divide-line p-0 text-[12.5px]">
      <div className="p-3">
        <div className="label mb-2">Signed by the controller</div>
        {s === null ? (
          <p className="text-muted">No signed rule exists for this slot (the rule is not from the controller).</p>
        ) : (
          <ul className="mono space-y-1">
            {(rows ? rows.filter((r) => r.side !== "observed") : s.map((line) => ({ line, side: "both" as const }))).map((r) => (
              <li key={`s-${r.line}`} className={cn(r.side === "signed" && "rounded bg-ok/10 px-1 text-ok")}>
                {r.side === "signed" && <span className="sr-only">only in signed: </span>}
                {r.line}
              </li>
            ))}
          </ul>
        )}
        <p className="mono mt-2 flex items-center gap-2 text-muted"><TagStripe cookie={signedCookie} /> cookie {shortCookie(signedCookie)}</p>
      </div>
      <div className="p-3">
        <div className="label mb-2">On the switch now</div>
        {o === null ? (
          <p className="text-warn">Missing: the rule is not on the switch.</p>
        ) : (
          <ul className="mono space-y-1">
            {(rows ? rows.filter((r) => r.side !== "signed") : o.map((line) => ({ line, side: "both" as const }))).map((r) => (
              <li key={`o-${r.line}`} className={cn(r.side === "observed" && "rounded bg-danger/10 px-1 text-danger")}>
                {r.side === "observed" && <span className="sr-only">only on the switch: </span>}
                {r.line}
              </li>
            ))}
          </ul>
        )}
        <p className="mono mt-2 flex items-center gap-2 text-muted">{present && <TagStripe cookie={observedCookie} against={signedCookie ?? null} />} cookie {present ? shortCookie(observedCookie) : "—"}</p>
      </div>
    </DataSurface>
  );
}
