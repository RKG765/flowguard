import { useCallback, useState } from "react";

/** Minimal list virtualization for fixed-height rows: renders only the rows in view (plus overscan), so tables with
 *  thousands of rules stay fast. Returns the slice to render and the spacer heights above/below it. */
export function useWindow(count: number, rowHeight: number, viewport: number, overscan = 8) {
  const [scrollTop, setScrollTop] = useState(0);
  const onScroll = useCallback((e: React.UIEvent<HTMLElement>) => setScrollTop(e.currentTarget.scrollTop), []);
  const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const last = Math.min(count, Math.ceil((scrollTop + viewport) / rowHeight) + overscan);
  return { first, last, padTop: first * rowHeight, padBottom: (count - last) * rowHeight, onScroll };
}
