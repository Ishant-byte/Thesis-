import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { get, post } from "../lib/api";
import { PageHeader, Alert, Card } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface Notice {
  _id: string;
  title: string;
  body: string;
  created_by: string;
  created_at: string;
}

export function NoticesPage() {
  const { session } = useAuth();
  const isAdmin = session?.role === "admin";
  const [notices, setNotices] = useState<Notice[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const refresh = async () => {
    if (!session) return;
    try {
      const data = await get<{ notices: Notice[] }>("/notices", session.token);
      setNotices(data.notices ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    refresh();
  }, [session]);

  const publish = async () => {
    if (!session) return;
    try {
      await post("/admin/notices", { title, body }, session.token);
      setMsg("Notice published.");
      setTitle("");
      setBody("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    }
  };

  return (
    <div>
      <PageHeader title="Company Notices" description="Official announcements and updates." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}
      {msg && <div className="mb-4"><Alert type="success">{msg}</Alert></div>}

      {isAdmin && (
        <Card className="mb-6 max-w-2xl">
          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <div className="mt-4">
            <label className="label">Body</label>
            <textarea
              className="input-field min-h-[100px]"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          <div className="mt-4">
            <Button onClick={publish}>Publish Notice</Button>
          </div>
        </Card>
      )}

      <div className="space-y-4">
        {notices.length === 0 ? (
          <Card><p className="text-sm text-slate-400">No notices yet.</p></Card>
        ) : (
          notices.map((n) => (
            <Card key={n._id}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="font-medium text-slate-900">{n.title}</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{n.body}</p>
                </div>
                <div className="shrink-0 text-right text-xs text-slate-400">
                  <div>{new Date(n.created_at).toLocaleDateString()}</div>
                  <div>{n.created_by}</div>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
