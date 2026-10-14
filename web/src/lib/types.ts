import type { Instruction, Match } from "./format";

/** Shapes returned by the core API for the Phase 4 pages (core/api/data.py). */
export interface RuleRow {
  dpid: string;
  table_id: number;
  priority: number;
  match: Match;
  instructions: Instruction[];
  cookie: string | null;
  status: "ok" | "altered" | "shadow" | "forged" | "missing" | "pending";
  golden: boolean;
  golden_cookie: string | null;
  golden_instructions?: Instruction[] | null;
  present: boolean;
  last_verified: number;
}

export interface Alert {
  id: string;
  seq: number | null;
  t: number;
  kind: string;
  severity: string;
  layer: string;
  dpid: string | null;
  table_id: number | null;
  priority: number | null;
  action: string | null;
  detected_by: string | null;
  summary: string | null;
  detect_latency_ms: number | null;
  time_to_restore_ms: number | null;
  restored_at: number | null;
  status: "new" | "acknowledged";
  acknowledged_by: string | null;
  incident_id: number | null;
}

export interface AlertDetails {
  match?: Match;
  reasons?: string[];
  shadows?: string[];
  signature_valid?: boolean | null;
  observed?: { cookie: string; instructions: Instruction[] } | null;
  golden?: { cookie: string; instructions: Instruction[] } | null;
  timing?: Record<string, number | null>;
  events?: { event: string; cookie: string | null; match: string; t: number }[];
  action_reason?: string;
}
export type AlertFull = Alert & { details: AlertDetails };

export interface IncidentDetail {
  id: number;
  title: string;
  severity: string;
  status: "open" | "acknowledged" | "closed";
  dpid: string | null;
  assignee: string | null;
  alert_count: number;
  created_at: number;
  updated_at: number;
  closed_at: number | null;
  alerts: Alert[];
  notes: { id: number; t: number; username: string; text: string }[];
}

export interface SwitchRow {
  dpid: string;
  name: string | null;
  connected: boolean;
  monitor_up: boolean;
  first_seen: number;
  last_seen: number;
  open_incidents: number;
}

export interface EngineStatusFull {
  known: boolean;
  age_seconds?: number | null;
  stale?: boolean;
  status?: {
    switches: string[];
    monitors_up: Record<string, boolean>;
    epoch: number;
    golden_rules: number;
    response_mode?: "restore" | "alert_only";
    hosts?: Record<string, Record<string, number>>;
    counters?: Record<string, number>;
  };
}
