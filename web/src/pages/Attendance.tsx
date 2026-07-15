import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { get, post } from "../lib/api";
import { PageHeader, Alert, Table, Card } from "../components/ui";
import { Button } from "../components/Button";

interface Record {
  date: string;
  clock_in?: string | null;
  clock_out?: string | null;
}

export function AttendancePage() {
  const { session } = useAuth();
  const [records, setRecords] = useState<Record[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const refresh = async () => {
    if (!session) return;
    try {
      const data = await get<{ records: Record[] }>("/me/attendance", session.token);
      setRecords(data.records ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    refresh();
  }, [session]);

  const clock = async (action: "clock_in" | "clock_out") => {
    if (!session) return;
    setError("");
    setMsg("");
    try {
      await post("/me/attendance", { action }, session.token);
      setMsg(action === "clock_in" ? "Clocked in successfully." : "Clocked out successfully.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    }
  };

  const fmt = (v?: string | null) => {
    if (!v) return "—";
    try {
      return new Date(v).toLocaleString();
    } catch {
      return v;
    }
  };

  return (
    <div>
      <PageHeader title="Attendance" description="Track your daily clock-in and clock-out times." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}
      {msg && <div className="mb-4"><Alert type="success">{msg}</Alert></div>}

      <Card className="mb-6">
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => clock("clock_in")}>Clock In</Button>
          <Button variant="secondary" onClick={() => clock("clock_out")}>Clock Out</Button>
          <Button variant="secondary" onClick={refresh}>Refresh</Button>
        </div>
      </Card>

      <Table
        headers={["Date", "Clock In", "Clock Out"]}
        rows={records.map((r) => [r.date, fmt(r.clock_in), fmt(r.clock_out)])}
      />
    </div>
  );
}
