import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { get, put, downloadBlob } from "../lib/api";
import { DEPARTMENTS } from "../lib/constants";
import { PageHeader, Alert, Select, Card } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

interface Profile {
  first_name: string;
  last_name: string;
  department: string;
  phone: string;
  address: string;
}

export function ProfilePage() {
  const { session } = useAuth();
  const [profile, setProfile] = useState<Profile>({
    first_name: "",
    last_name: "",
    department: "HR",
    phone: "",
    address: "",
  });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!session) return;
    try {
      const p = await get<Profile>("/me/profile", session.token);
      setProfile({
        first_name: p.first_name ?? "",
        last_name: p.last_name ?? "",
        department: p.department ?? "HR",
        phone: p.phone ?? "",
        address: p.address ?? "",
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load profile");
    }
  };

  useEffect(() => {
    load();
  }, [session]);

  const save = async () => {
    if (!session) return;
    setLoading(true);
    setError("");
    setMsg("");
    try {
      await put("/me/profile", profile, session.token);
      setMsg("Profile saved successfully.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setLoading(false);
    }
  };

  const downloadKeystore = async () => {
    if (!session) return;
    try {
      const blob = await downloadBlob("/me/keystore", session.token);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "keystore.p12";
      a.click();
      URL.revokeObjectURL(url);
      setMsg("Keystore downloaded. Keep this file secure for future logins.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    }
  };

  return (
    <div>
      <PageHeader title="Profile" description="Manage your personal information and certificate keystore." />
      {error && <Alert type="error">{error}</Alert>}
      {msg && <div className="mb-4"><Alert type="success">{msg}</Alert></div>}

      <Card className="max-w-2xl">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="First Name" value={profile.first_name} onChange={(e) => setProfile({ ...profile, first_name: e.target.value })} />
          <Input label="Last Name" value={profile.last_name} onChange={(e) => setProfile({ ...profile, last_name: e.target.value })} />
          <Select label="Department" value={profile.department} onChange={(v) => setProfile({ ...profile, department: v })} options={[...DEPARTMENTS]} />
          <Input label="Phone" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} />
          <div className="sm:col-span-2">
            <Input label="Address" value={profile.address} onChange={(e) => setProfile({ ...profile, address: e.target.value })} />
          </div>
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button onClick={save} disabled={loading}>{loading ? "Saving…" : "Save Changes"}</Button>
          <Button variant="secondary" onClick={load}>Refresh</Button>
          <Button variant="secondary" onClick={downloadKeystore}>Download Keystore (.p12)</Button>
        </div>
      </Card>
    </div>
  );
}
