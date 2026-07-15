import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { health, post } from "../lib/api";
import { EMAIL_RE, validatePassword, DEPARTMENTS, ADMIN_ROLES, EMPLOYEE_ROLES } from "../lib/constants";
import { Card, Alert, Select } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

export function RegisterPage() {
  const { role } = useParams<{ role: string }>();
  const portalRole = role === "admin" ? "admin" : "employee";
  const navigate = useNavigate();

  const [form, setForm] = useState({
    username: "",
    password: "",
    password2: "",
    first_name: "",
    last_name: "",
    job_role: portalRole === "admin" ? ADMIN_ROLES[0] : EMPLOYEE_ROLES[0],
    department: portalRole === "admin" ? "Security" : DEPARTMENTS[0],
    phone: "",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setError("");
    setSuccess("");
    if (!EMAIL_RE.test(form.username.trim())) {
      setError("Username must be a valid email address.");
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
      await post("/auth/register", {
        username: form.username.trim(),
        password: form.password,
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        job_role: form.job_role,
        department: form.department,
        phone: form.phone.trim() || null,
        role: portalRole,
      });
      setSuccess(
        "Registration successful. Your keystore was created at pki/users/<username>/keystore.p12 on the server. Use it during login."
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const roleOptions = portalRole === "admin" ? [...ADMIN_ROLES] : [...EMPLOYEE_ROLES];

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <Card className="w-full max-w-lg">
        <Link
          to={`/portal/${portalRole}`}
          className="mb-6 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>

        <h1 className="text-2xl font-semibold text-slate-900">
          {portalRole === "admin" ? "Admin" : "Employee"} Registration
        </h1>
        <p className="mt-1 text-sm text-slate-500">Create an account with a strong password.</p>

        {error && (
          <div className="mt-4">
            <Alert type="error">{error}</Alert>
          </div>
        )}
        {success && (
          <div className="mt-4 space-y-3">
            <Alert type="success">{success}</Alert>
            <Button className="w-full" onClick={() => navigate(`/login/${portalRole}`)}>
              Go to Sign In
            </Button>
          </div>
        )}

        {!success && (
          <>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <Input label="Email" type="email" value={form.username} onChange={(e) => set("username", e.target.value)} />
              <Input label="Phone (optional)" value={form.phone} onChange={(e) => set("phone", e.target.value)} />
              <Input label="Password" type="password" value={form.password} onChange={(e) => set("password", e.target.value)} />
              <Input label="Confirm Password" type="password" value={form.password2} onChange={(e) => set("password2", e.target.value)} />
              <Input label="First Name" value={form.first_name} onChange={(e) => set("first_name", e.target.value)} />
              <Input label="Last Name" value={form.last_name} onChange={(e) => set("last_name", e.target.value)} />
              <Select label="Job Role" value={form.job_role} onChange={(v) => set("job_role", v)} options={roleOptions} />
              <Select label="Department" value={form.department} onChange={(v) => set("department", v)} options={[...DEPARTMENTS]} />
            </div>
            <div className="mt-6">
              <Button className="w-full" onClick={submit} disabled={loading}>
                {loading ? "Creating account…" : "Create Account"}
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
