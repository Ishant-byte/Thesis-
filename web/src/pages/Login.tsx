import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { health, post } from "../lib/api";
import { getCertFromP12, signTextP12, loadKeystoreFromFile } from "../lib/crypto";
import { useAuth } from "../lib/auth";
import { Card, Alert } from "../components/ui";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

export function LoginPage() {
  const { role } = useParams<{ role: string }>();
  const portalRole = role === "admin" ? "admin" : "employee";
  const navigate = useNavigate();
  const { setSession } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [otpToken, setOtpToken] = useState("");
  const [nonce, setNonce] = useState("");
  const [keystoreFile, setKeystoreFile] = useState<File | null>(null);
  const [step, setStep] = useState<"credentials" | "verify">("credentials");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [otpHint, setOtpHint] = useState("");

  const requestOtp = async () => {
    setError("");
    setLoading(true);
    try {
      await health();
      const resp = await post<{ otp_token: string; nonce: string; otp_code?: string }>(
        "/auth/request-otp",
        { username: username.trim(), password }
      );
      setOtpToken(resp.otp_token);
      setNonce(resp.nonce);
      if (resp.otp_code) setOtpHint(resp.otp_code);
      setStep("verify");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const verifyLogin = async () => {
    if (!keystoreFile) {
      setError("Upload your keystore (.p12) file to complete certificate verification.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const p12Bytes = await loadKeystoreFromFile(keystoreFile);
      const cert = getCertFromP12(p12Bytes, password);
      const commonName = cert.subject.getField("CN")?.value;
      if (commonName && commonName !== username.trim()) {
        throw new Error(`This keystore belongs to ${commonName}, not ${username.trim()}.`);
      }
      const signature_b64 = await signTextP12(p12Bytes, password, nonce);
      const resp = await post<{ access_token: string; role: "admin" | "employee" }>(
        "/auth/verify",
        { otp_token: otpToken, otp_code: otp.trim(), signature_b64 }
      );
      setSession({
        token: resp.access_token,
        role: resp.role,
        username: username.trim(),
        keystore: p12Bytes,
        keystorePassword: password,
      });
      navigate("/dashboard/profile");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <Card className="w-full max-w-md">
        <Link
          to={`/portal/${portalRole}`}
          className="mb-6 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>

        <h1 className="text-2xl font-semibold text-slate-900">Sign In</h1>
        <p className="mt-1 text-sm capitalize text-slate-500">{portalRole} portal</p>

        {error && (
          <div className="mt-4">
            <Alert type="error">{error}</Alert>
          </div>
        )}

        <div className="mt-6 space-y-4">
          <Input
            label="Email"
            type="email"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={step === "verify"}
            placeholder="you@company.com"
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />

          {step === "verify" && (
            <>
              {otpHint && (
                <Alert type="info">
                  Demo OTP: <strong>{otpHint}</strong> (also printed on server console)
                </Alert>
              )}
              <Input
                label="One-Time Password"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                placeholder="6-digit code"
              />
              <div>
                <label className="label">Certificate Keystore (.p12)</label>
                <input
                  type="file"
                  accept=".p12,.pfx"
                  className="input-field"
                  onChange={(e) => setKeystoreFile(e.target.files?.[0] ?? null)}
                />
                <p className="mt-1 text-xs text-slate-400">
                  Located at pki/users/&lt;username&gt;/keystore.p12 after registration
                </p>
              </div>
            </>
          )}
        </div>

        <div className="mt-6">
          {step === "credentials" ? (
            <Button className="w-full" onClick={requestOtp} disabled={loading || !username || !password}>
              {loading ? "Requesting…" : "Request OTP"}
            </Button>
          ) : (
            <Button className="w-full" onClick={verifyLogin} disabled={loading || !otp}>
              {loading ? "Signing in…" : "Verify & Sign In"}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
