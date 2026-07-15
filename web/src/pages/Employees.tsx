import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { get, post, del } from "../lib/api";
import { DEPARTMENTS } from "../lib/constants";
import { PageHeader, Alert, Table, Card, Select } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface User {
  username: string;
  role: string;
  presence_state: string;
  department?: string;
  cert_serial?: string;
}

interface CreateUserForm {
  username: string;
  password: string;
  first_name: string;
  last_name: string;
  department: string;
  phone: string;
  role: string;
}

export function EmployeesPage() {
  const { session } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [selected, setSelected] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateUserForm>({
    username: "",
    password: "",
    first_name: "",
    last_name: "",
    department: DEPARTMENTS[0],
    phone: "",
    role: "employee",
  });
  const [revokeReason, setRevokeReason] = useState("compromised");
  const [rotatePassword, setRotatePassword] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const refresh = async () => {
    if (!session) return;
    try {
      const data = await get<{ users: User[] }>("/admin/users", session.token);
      setUsers(data.users ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    refresh();
  }, [session]);

  const createUser = async () => {
    if (!session) return;
    try {
      await post("/admin/users/create", { ...form, phone: form.phone || null }, session.token);
      setMsg("User created. Keystore saved on server.");
      setShowCreate(false);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    }
  };

  const deleteUser = async () => {
    if (!session || !selected) return;
    if (!confirm(`Delete ${selected}?`)) return;
    try {
      await del(`/admin/users/${selected}`, session.token);
      setMsg("User deleted.");
      setSelected("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const revokeCert = async () => {
    if (!session || !selected) return;
    try {
      await post(`/admin/users/${selected}/revoke-cert`, { reason: revokeReason }, session.token);
      setMsg("Certificate revoked.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Revoke failed");
    }
  };

  const rotateCert = async () => {
    if (!session || !selected || !rotatePassword) return;
    try {
      const resp = await post<{ pkcs12_path: string }>(
        `/admin/users/${selected}/rotate-cert`,
        { new_password: rotatePassword },
        session.token
      );
      setMsg(`Certificate rotated. New keystore: ${resp.pkcs12_path}`);
      setRotatePassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rotate failed");
    }
  };

  return (
    <div>
      <PageHeader title="Employees & Admins" description="Manage user accounts and PKI certificates." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}
      {msg && <div className="mb-4"><Alert type="success">{msg}</Alert></div>}

      <Card className="mb-6">
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={refresh}>Refresh</Button>
          <Button onClick={() => setShowCreate(!showCreate)}>{showCreate ? "Cancel" : "Create User"}</Button>
        </div>
      </Card>

      {showCreate && (
        <Card className="mb-6 max-w-2xl">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Email" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            <Input label="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <Input label="First Name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            <Input label="Last Name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            <Select label="Department" value={form.department} onChange={(v) => setForm({ ...form, department: v })} options={[...DEPARTMENTS]} />
            <Select label="Account Role" value={form.role} onChange={(v) => setForm({ ...form, role: v })} options={["employee", "admin"]} />
            <Input label="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="mt-4">
            <Button onClick={createUser}>Create User</Button>
          </div>
        </Card>
      )}

      <Table
        headers={["Role", "Status", "Department", "Username"]}
        rows={users.map((u) => [
          u.role,
          u.presence_state ?? "offline",
          u.department ?? "—",
          <button key={u.username} className="text-brand-700 hover:underline" onClick={() => setSelected(u.username)}>
            {u.username}
          </button>,
        ])}
      />

      {selected && (
        <Card className="mt-6">
          <h3 className="mb-4 font-medium text-slate-900">Actions for {selected}</h3>
          <div className="flex flex-wrap items-end gap-4">
            <Input label="Revoke Reason" value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)} className="max-w-xs" />
            <Button variant="secondary" onClick={revokeCert}>Revoke Certificate</Button>
            <Input label="New Keystore Password" type="password" value={rotatePassword} onChange={(e) => setRotatePassword(e.target.value)} className="max-w-xs" />
            <Button variant="secondary" onClick={rotateCert}>Rotate Certificate</Button>
            <Button variant="danger" onClick={deleteUser}>Delete User</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
