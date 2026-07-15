import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { get, post } from "../lib/api";
import { PageHeader, Alert, Table, Card } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface SalaryRecord {
  month: string;
  amount: number | string;
  note?: string;
  created_at?: string;
}

export function SalaryPage() {
  const { session } = useAuth();
  const isAdmin = session?.role === "admin";
  const [records, setRecords] = useState<SalaryRecord[]>([]);
  const [username, setUsername] = useState("");
  const [form, setForm] = useState({ month: "", amount: "", note: "" });
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const refresh = async (target?: string) => {
    if (!session) return;
    try {
      const path = isAdmin ? `/admin/salary/${target || username}` : "/me/salary";
      if (isAdmin && !target && !username) {
        setRecords([]);
        return;
      }
      const data = await get<{ records: SalaryRecord[] }>(path, session.token);
      setRecords(data.records ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    if (!isAdmin) refresh();
  }, [session]);

  const addSalary = async () => {
    if (!session || !username) return;
    setError("");
    try {
      await post(
        `/admin/salary/${username.trim()}`,
        { month: form.month, amount: parseFloat(form.amount), note: form.note || null },
        session.token
      );
      setMsg("Salary record added.");
      refresh(username.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add");
    }
  };

  return (
    <div>
      <PageHeader
        title="Salary & Payroll"
        description={isAdmin ? "Manage employee salary records." : "View your salary history."}
      />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}
      {msg && <div className="mb-4"><Alert type="success">{msg}</Alert></div>}

      {isAdmin && (
        <Card className="mb-6 max-w-2xl">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Employee Email" value={username} onChange={(e) => setUsername(e.target.value)} />
            <Input label="Month (YYYY-MM)" value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })} placeholder="2026-01" />
            <Input label="Amount" type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            <Input label="Note" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </div>
          <div className="mt-4 flex gap-3">
            <Button onClick={addSalary}>Add Record</Button>
            <Button variant="secondary" onClick={() => refresh(username.trim())}>Load Records</Button>
          </div>
        </Card>
      )}

      <Table
        headers={["Month", "Amount", "Note", "Created"]}
        rows={records.map((r) => [
          r.month,
          String(r.amount),
          r.note ?? "—",
          r.created_at ? new Date(r.created_at).toLocaleDateString() : "—",
        ])}
      />
    </div>
  );
}
