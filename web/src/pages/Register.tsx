import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { downloadBase64File, health, post } from "../lib/api";
import { validatePassword } from "../lib/constants";
import { Card, Alert } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

export function RegisterPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form, setForm] = useState({
    token: searchParams.get("token") ?? "",
    password: "",
    password2: "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [activatedRole, setActivatedRole] = useState<"admin" | "employee">("employee");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = searchParams.get("token") ?? "";
    setForm((current) => (current.token === token ? current : { ...current, token }));
  }, [searchParams]);

  const set = (k: keyof typeof form, v: string) => setForm((current) => ({ ...current, [k]: v }));

  const submit = async () => {
    setError("");
    setSuccess("");
    if (!form.token.trim()) {
      setError("Activation token is required.");
      return;
    }
    if (form.password !== form.password2) {
      setError("Passwords do not match.");
      return;
    }
    const pwErr = validatePassword(form.password);
    if (pwErr) {
      setError(pwErr);
      return;
    }
    setLoading(true);
    try {
      await health();
      const result = await post<{ keystore_b64: string; keystore_filename: string; role: "admin" | "employee" }>(
        "/auth/activate",
        { token: form.token.trim(), password: form.password }
      );
      downloadBase64File(result.keystore_b64, result.keystore_filename);
      setActivatedRole(result.role);
      setSuccess("Activation successful. Your keystore has been downloaded. Keep it secure because you need it to sign in.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Activation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <Card className="w-full max-w-lg">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>

        <h1 className="text-2xl font-semibold text-slate-900">Activate Account</h1>
        <p className="mt-1 text-sm text-slate-500">
          Use the one-time activation token from your administrator, then choose your own password.
        </p>

        {error && (
          <div className="mt-4">
            <Alert type="error">{error}</Alert>
          </div>
        )}
        {success && (
          <div className="mt-4 space-y-3">
            <Alert type="success">{success}</Alert>
            <Button className="w-full" onClick={() => navigate(`/login/${activatedRole === "employee" ? "employee" : "admin"}`)}>
              Go to Sign In
            </Button>
          </div>
        )}

        {!success && (
          <>
            <div className="mt-6 grid gap-4">
              <Input
                label="Activation Token"
                value={form.token}
                onChange={(e) => set("token", e.target.value)}
                placeholder="Paste your one-time token"
              />
              <Input
                label="Password"
                type="password"
                value={form.password}
                onChange={(e) => set("password", e.target.value)}
              />
              <Input
                label="Confirm Password"
                type="password"
                value={form.password2}
                onChange={(e) => set("password2", e.target.value)}
              />
            </div>
            <div className="mt-6">
              <Button className="w-full" onClick={submit} disabled={loading}>
                {loading ? "Activating..." : "Activate Account"}
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
