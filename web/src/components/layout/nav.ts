import {
  Activity, Bell, BookOpen, Brain, Eye, FileBarChart2, LayoutDashboard, Network, Radar, ScrollText, Settings, ShieldHalf,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** phase in which the page gets real content; until then it shows an honest "planned" page */
  phase: number;
  /** built and routed (pages still to come render the Planned page) */
  built?: boolean;
  keywords?: string;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, phase: 3, keywords: "home dashboard health" },
  { to: "/topology", label: "Topology", icon: Network, phase: 4, built: true, keywords: "switches hosts links graph" },
  { to: "/rules", label: "Rules", icon: ShieldHalf, phase: 4, built: true, keywords: "rule inspector flows integrity" },
  { to: "/alerts", label: "Alerts", icon: Bell, phase: 4, built: true, keywords: "incidents triage" },
  { to: "/live", label: "Live Detection", icon: Eye, phase: 4, built: true, keywords: "live detections observation response timings" },
  { to: "/probes", label: "Probes", icon: Radar, phase: 5, keywords: "l2 canary data plane" },
  { to: "/ml", label: "ML", icon: Brain, phase: 5, keywords: "l3 anomaly score model" },
  { to: "/policy", label: "Policy", icon: Activity, phase: 6, keywords: "risk weights thresholds" },
  { to: "/reports", label: "Reports", icon: FileBarChart2, phase: 6, keywords: "pdf csv export" },
  { to: "/audit", label: "Audit", icon: ScrollText, phase: 6, keywords: "audit log who what when" },
  { to: "/settings", label: "Settings", icon: Settings, phase: 6, keywords: "users keys environment" },
  { to: "/design", label: "Design system", icon: BookOpen, phase: 3, keywords: "components style guide tokens" },
];
