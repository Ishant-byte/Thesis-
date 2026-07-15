import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { get } from "../lib/api";
import { PageHeader, Alert, Table, Card } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface LogEntry {
  timestamp: string;
  severity: string;
  event_type: string;
  actor_username?: string;
  target_username?: string;
  message: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export function LogsPage() {
  const { session } = useAuth();
  const isAdmin = session?.role === "admin";
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filters, setFilters] = useState({ actor: "", target: "", event_type: "", start: "", end: "" });
  const [error, setError] = useState("");

  const refresh = async () => {
    if (!session) return;
    setError("");
    try {
      const params: Record<string, string> = {};
      if (filters.actor) params.actor = filters.actor;
      if (filters.target) params.target = filters.target;
      if (filters.event_type) params.event_type = filters.event_type;
      if (filters.start) params.start = filters.start;
      if (filters.end) params.end = filters.end;

      const path = isAdmin ? "/admin/logs" : "/me/logs";
      const data = await get<{ logs: LogEntry[] }>(path, session.token, Object.keys(params).length ? params : undefined);
      setLogs(data.logs ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load logs");
    }
  };

  useEffect(() => {
    refresh();
  }, [session]);

  const exportCsv = async () => {
    if (!session || !isAdmin) return;
    const params = new URLSearchParams();
    if (filters.actor) params.set("actor", filters.actor);
    if (filters.target) params.set("target", filters.target);
    if (filters.event_type) params.set("event_type", filters.event_type);
    if (filters.start) params.set("start", filters.start);
    if (filters.end) params.set("end", filters.end);
    const r = await fetch(`${API_BASE}/admin/logs/export?${params}`, {
      headers: { Authorization: `Bearer ${session.token}` },
    });
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit_logs.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <PageHeader
        title={isAdmin ? "Audit Logs" : "My Activity Logs"}
        description={isAdmin ? "Security and system event audit trail." : "Your account activity history."}
      />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}

      {isAdmin && (
        <Card className="mb-6">
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <Input label="Actor" value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} />
            <Input label="Target" value={filters.target} onChange={(e) => setFilters({ ...filters, target: e.target.value })} />
            <Input label="Event Type" value={filters.event_type} onChange={(e) => setFilters({ ...filters, event_type: e.target.value })} />
            <Input label="Start (ISO)" value={filters.start} onChange={(e) => setFilters({ ...filters, start: e.target.value })} />
            <Input label="End (ISO)" value={filters.end} onChange={(e) => setFilters({ ...filters, end: e.target.value })} />
          </div>
          <div className="mt-4 flex gap-3">
            <Button variant="secondary" onClick={refresh}>Apply Filters</Button>
            <Button variant="secondary" onClick={exportCsv}>Export CSV</Button>
          </div>
        </Card>
      )}

      <Table
        headers={["Timestamp", "Severity", "Event", "Actor", "Target", "Message"]}
        rows={logs.map((l) => [
          new Date(l.timestamp).toLocaleString(),
          l.severity,
          l.event_type,
          l.actor_username ?? "—",
          l.target_username ?? "—",
          l.message,
        ])}
      />
    </div>
  );
}
