import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { get, post } from "../lib/api";
import { PageHeader, Alert, Table, Card } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface LeaveRequest {
  _id: string;
  status: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  username?: string;
  reason?: string;
}

export function LeavePage() {
  const { session } = useAuth();
  const isAdmin = session?.role === "admin";
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [form, setForm] = useState({ leave_type: "", start_date: "", end_date: "", reason: "" });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const refresh = async () => {
    if (!session) return;
    try {
      const path = isAdmin ? "/admin/leave" : "/me/leave";
      const data = await get<{ requests: LeaveRequest[] }>(path, session.token);
      setRequests(data.requests ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    refresh();
  }, [session]);

  const submit = async () => {
    if (!session) return;
    setError("");
    try {
      await post("/me/leave", form, session.token);
      setMsg("Leave request submitted.");
      setForm({ leave_type: "", start_date: "", end_date: "", reason: "" });
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submit failed");
    }
  };

  const decide = async (decision: "approve" | "reject") => {
    if (!session || !selectedId) return;
    try {
      await post(`/admin/leave/${selectedId}`, { decision }, session.token);
      setMsg(`Leave ${decision === "approve" ? "approved" : "rejected"}.`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    }
  };

  return (
    <div>
      <PageHeader
        title="Leave Management"
        description={isAdmin ? "Review and approve employee leave requests." : "Submit and track your leave requests."}
      />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}
      {msg && <div className="mb-4"><Alert type="success">{msg}</Alert></div>}

      {!isAdmin && (
        <Card className="mb-6 max-w-2xl">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Type" placeholder="Sick / Vacation" value={form.leave_type} onChange={(e) => setForm({ ...form, leave_type: e.target.value })} />
            <Input label="Reason" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            <Input label="Start Date" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            <Input label="End Date" type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
          </div>
          <div className="mt-4">
            <Button onClick={submit}>Submit Request</Button>
          </div>
        </Card>
      )}

      {isAdmin && (
        <Card className="mb-6">
          <div className="flex flex-wrap items-end gap-3">
            <Input label="Selected Leave ID" value={selectedId} onChange={(e) => setSelectedId(e.target.value)} className="max-w-md" />
            <Button onClick={() => decide("approve")}>Approve</Button>
            <Button variant="danger" onClick={() => decide("reject")}>Reject</Button>
            <Button variant="secondary" onClick={refresh}>Refresh</Button>
          </div>
        </Card>
      )}

      <Table
        headers={isAdmin ? ["Status", "Employee", "Type", "Dates", "ID"] : ["Status", "Type", "Start", "End", "ID"]}
        rows={requests.map((r) =>
          isAdmin
            ? [r.status, r.username ?? "—", r.leave_type, `${r.start_date} → ${r.end_date}`, r._id]
            : [r.status, r.leave_type, r.start_date, r.end_date, r._id]
        )}
      />
    </div>
  );
}
