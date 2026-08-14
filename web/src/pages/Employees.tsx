import { useEffect, useRef, useState } from "react";
import { useAuth } from "../lib/auth";
import { get, post, downloadBase64File } from "../lib/api";
import { DEPARTMENTS } from "../lib/constants";
import { PageHeader, Alert, Table, Card, Select } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface User {
  username: string;
  role: string;
  active: boolean;
  activation_pending?: boolean;
  activation_expires_at?: string;
  presence_state: string;
  department?: string;
  cert_serial?: string;
}

interface CreateUserForm {
  username: string;
  first_name: string;
  last_name: string;
  department: string;
  phone: string;
  role: string;
}

export function EmployeesPage() {
  const { session } = useAuth();
  const isSuperAdmin = session?.role === "super_admin";
  const [users, setUsers] = useState<User[]>([]);
  const [selected, setSelected] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateUserForm>({
    username: "",
    first_name: "",
    last_name: "",
    department: DEPARTMENTS[0],
    phone: "",
    role: "employee",
  });
  const [activationResult, setActivationResult] = useState<{
    username: string;
    token: string;
    expiresAt: string;
  } | null>(null);
  const [revokeReason, setRevokeReason] = useState("compromised");
  const [rotatePassword, setRotatePassword] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [copiedField, setCopiedField] = useState<"link" | "token" | "">("");
  const actionsRef = useRef<HTMLDivElement>(null);
  const selectedUser = users.find((user) => user.username === selected);
  const canManageSelected = selectedUser?.role === "employee" || (isSuperAdmin && selectedUser?.role === "admin");
  const selectedIsPendingActivation = Boolean(selectedUser?.activation_pending);
  const canDeactivateSelected = Boolean(
    selectedUser && canManageSelected && selectedUser.active && selectedUser.username !== session?.username
  );
  const canReactivateSelected = Boolean(
    selectedUser &&
      canManageSelected &&
      !selectedUser.active &&
      !selectedIsPendingActivation &&
      selectedUser.username !== session?.username
  );

  const activationLink = activationResult
    ? `${window.location.origin}/activate?token=${encodeURIComponent(activationResult.token)}`
    : "";

  const accountStatus = (user: User) => {
    if (user.active) return "Active";
    if (user.activation_pending) return "Pending activation";
    return "Inactive";
  };

  const refresh = async (announce = false) => {
    if (!session) return;
    setRefreshing(true);
    setError("");
    try {
      const data = await get<{ users: User[] }>("/admin/users", session.token);
      setUsers(data.users ?? []);
      if (announce) setMsg("Employee list refreshed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [session]);

  useEffect(() => {
    if (selected) actionsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selected]);

  const copyActivationValue = async (kind: "link" | "token", value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(kind);
      window.setTimeout(() => {
        setCopiedField((current) => (current === kind ? "" : current));
      }, 2000);
    } catch {
      setError("Copy failed. Copy the activation details manually.");
    }
  };

  const createUser = async () => {
    if (!session) return;
    try {
      setError("");
      setMsg("");
      const result = await post<{ activation_token: string; activation_expires_at: string }>(
        "/admin/users/create",
        { ...form, phone: form.phone || null },
        session.token
      );
      setActivationResult({
        username: form.username.trim(),
        token: result.activation_token,
        expiresAt: result.activation_expires_at,
      });
      setMsg("User created in pending activation. Share the one-time activation link securely.");
      setShowCreate(false);
      setForm({
        username: "",
        first_name: "",
        last_name: "",
        department: DEPARTMENTS[0],
        phone: "",
        role: "employee",
      });
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    }
  };

  const deactivateUser = async () => {
    if (!session || !selectedUser || !canDeactivateSelected) return;
    if (
      !confirm(
        `Deactivate ${selectedUser.username}? This will disable account access immediately and revoke the current certificate.`
      )
    ) return;
    try {
      await post(`/admin/users/${selectedUser.username}/deactivate`, { reason: "offboarding" }, session.token);
      setMsg("Account deactivated and current certificate revoked.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deactivate failed");
    }
  };

  const reactivateUser = async () => {
    if (!session || !selectedUser || !canReactivateSelected || !rotatePassword) return;
    if (
      !confirm(
        `Reactivate ${selectedUser.username}? A new certificate and keystore will be issued. The previous certificate will remain permanently revoked.`
      )
    ) return;
    try {
      const resp = await post<{ keystore_b64: string; keystore_filename: string }>(
        `/admin/users/${selectedUser.username}/reactivate`,
        { new_password: rotatePassword },
        session.token
      );
      downloadBase64File(resp.keystore_b64, resp.keystore_filename);
      setMsg("Account reactivated. The new keystore has been downloaded; transfer it securely.");
      setRotatePassword("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reactivate failed");
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
      const resp = await post<{ keystore_b64: string; keystore_filename: string }>(
        `/admin/users/${selected}/rotate-cert`,
        { new_password: rotatePassword },
        session.token
      );
      downloadBase64File(resp.keystore_b64, resp.keystore_filename);
      setMsg("Certificate rotated. The replacement keystore has been downloaded.");
      setRotatePassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rotate failed");
    }
  };

  return (
    <div>
      <PageHeader title="Employees & Admins" description="Manage user accounts and PKI certificates. Only a super admin can create administrators." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}
      {msg && <div className="mb-4"><Alert type="success">{msg}</Alert></div>}

      <Card className="mb-6">
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => refresh(true)} disabled={refreshing}>
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
          <Button
            onClick={() => {
              setShowCreate(!showCreate);
              setActivationResult(null);
            }}
          >
            {showCreate ? "Cancel" : "Create User"}
          </Button>
        </div>
      </Card>

      {activationResult && (
        <Card className="mb-6 max-w-3xl">
          <div className="space-y-4">
            <Alert type="success">
              {activationResult.username} is pending activation until{" "}
              {new Date(activationResult.expiresAt).toLocaleString()}.
            </Alert>
            <p className="text-sm text-slate-600">
              Share this one-time activation link or token securely. The user sets their own password during activation,
              and their certificate is issued only after activation succeeds.
            </p>
            <Alert type="info">
              This credential is single-use and expires at {new Date(activationResult.expiresAt).toLocaleString()}.
              Do not send it in a public channel.
            </Alert>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <Input label="Activation Link" value={activationLink} readOnly className="sm:flex-1" />
              <Button variant="secondary" onClick={() => copyActivationValue("link", activationLink)}>
                {copiedField === "link" ? "Copied" : "Copy Link"}
              </Button>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <Input label="Activation Token" value={activationResult.token} readOnly className="sm:flex-1" />
              <Button variant="secondary" onClick={() => copyActivationValue("token", activationResult.token)}>
                {copiedField === "token" ? "Copied" : "Copy Token"}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {showCreate && (
        <Card className="mb-6 max-w-2xl">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Email" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            <Input label="First Name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            <Input label="Last Name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            <Select label="Department" value={form.department} onChange={(v) => setForm({ ...form, department: v })} options={[...DEPARTMENTS]} />
            {isSuperAdmin && (
              <Select label="Account Role" value={form.role} onChange={(v) => setForm({ ...form, role: v })} options={["employee", "admin"]} />
            )}
            <Input label="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="mt-4 space-y-3">
            <Alert type="info">
              New accounts start inactive and pending activation.
            </Alert>
            <Button onClick={createUser}>Create User</Button>
          </div>
        </Card>
      )}

      <Table
        headers={["Role", "Account", "Presence", "Department", "Username", "Actions"]}
        rows={users.map((u) => [
          u.role,
          accountStatus(u),
          u.presence_state ?? "offline",
          u.department ?? "-",
          u.username,
          <Button key={u.username} variant="secondary" onClick={() => setSelected(u.username)}>Manage</Button>,
        ])}
      />

      {selected && (
        <div ref={actionsRef}>
        <Card className="mt-6">
          <h3 className="mb-4 font-medium text-slate-900">Actions for {selected}</h3>
          {canManageSelected ? (
            <div className="space-y-4">
              <Alert type="info">
                Account status: {selectedUser ? accountStatus(selectedUser) : "Unknown"}. Deactivation disables access
                and permanently revokes the current certificate. Reactivation issues a new certificate.
              </Alert>
              {selectedIsPendingActivation && (
                <Alert type="info">
                  This account is waiting for its one-time activation token to be used. It does not have a login password
                  or certificate yet.
                </Alert>
              )}
              {canDeactivateSelected && (
                <Button variant="danger" onClick={deactivateUser}>Deactivate Account</Button>
              )}
              {canReactivateSelected && (
                <div className="flex flex-wrap items-end gap-4">
                  <Input label="New Keystore Password" type="password" value={rotatePassword} onChange={(e) => setRotatePassword(e.target.value)} className="max-w-xs" />
                  <Button onClick={reactivateUser} disabled={!rotatePassword}>Reactivate & Issue New Certificate</Button>
                </div>
              )}
              {selectedUser?.active && <div className="flex flex-wrap items-end gap-4">
                <Input label="Revoke Reason" value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)} className="max-w-xs" />
                <Button variant="secondary" onClick={revokeCert}>Revoke Certificate</Button>
                <Input label="New Keystore Password" type="password" value={rotatePassword} onChange={(e) => setRotatePassword(e.target.value)} className="max-w-xs" />
                <Button variant="secondary" onClick={rotateCert}>Rotate Certificate</Button>
              </div>}
            </div>
          ) : (
            <Alert type="info">This privileged account can only be managed through the super-admin policy.</Alert>
          )}
        </Card>
        </div>
      )}
    </div>
  );
}
