import { useState } from "react";
import { zipSync } from "fflate";
import { useAuth } from "../lib/auth";
import { APIError, post } from "../lib/api";
import { sha256File, signBytesP12, getCertFromP12, certToPem, b64e, b64d } from "../lib/crypto";
import { PageHeader, Alert, Card } from "../components/ui";
import { Button } from "../components/Button";

interface BundleManifest {
  hash_alg: "SHA-256";
  purpose: "pramaanhr.document-signature";
  sha256_b64: string;
  signature_alg: "RSA-PSS-SHA256";
  signer_cert_sha256_b64: string;
  v: 2;
}

interface VerificationCheck {
  detail?: string;
  name: string;
  ok: boolean;
}

interface VerificationResult {
  checks: VerificationCheck[];
  message?: string;
  protocolVersion?: number;
  signer?: {
    serial?: string;
    username?: string;
  };
  verified: boolean;
}

interface VerificationApiResponse {
  checks?: Record<string, { detail: string; ok: boolean }>;
  detail?: string;
  message?: string;
  ok?: boolean;
  protocol_version?: number | null;
  signer_identity?: string | null;
  signer_serial?: string | null;
  status?: string;
  verified?: boolean;
}

export function DocumentsPage() {
  const { session } = useAuth();
  const [signFile, setSignFile] = useState<File | null>(null);
  const [verifyFile, setVerifyFile] = useState<File | null>(null);
  const [verifyBundle, setVerifyBundle] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [signing, setSigning] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState("");
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  const getKeystore = () => session?.keystore ?? null;

  const exportBundle = async () => {
    if (!signFile || !session) return;
    setError("");
    setVerifyMessage("");
    setVerifyResult(null);
    const ks = getKeystore();
    if (!ks) {
      setError("Keystore not loaded. Sign in with your .p12 file.");
      return;
    }
    const pw = password || session.keystorePassword;
    if (!pw) {
      setError("Enter your keystore password.");
      return;
    }
    setSigning(true);
    try {
      const digest = await sha256File(signFile);
      const cert = getCertFromP12(ks, pw);
      const certPem = certToPem(cert);
      const manifest: BundleManifest = {
        hash_alg: "SHA-256",
        purpose: "pramaanhr.document-signature",
        sha256_b64: b64e(digest),
        signature_alg: "RSA-PSS-SHA256",
        signer_cert_sha256_b64: await certFingerprintSha256B64(certPem),
        v: 2,
      };
      const manifestJson = canonicalJson(manifest);
      const sigB64 = await signBytesP12(ks, pw, new TextEncoder().encode(manifestJson));
      const zip = buildBundleZip({
        "manifest.json": new TextEncoder().encode(manifestJson),
        "signature.sig": b64d(sigB64),
        "signer_cert.pem": new TextEncoder().encode(certPem),
      });
      const url = URL.createObjectURL(zip);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${signFile.name}.signature.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
      setVerifyMessage(`Exported v2 signature bundle for ${signFile.name}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Signing failed");
    } finally {
      setSigning(false);
    }
  };

  const verify = async () => {
    if (!verifyFile || !verifyBundle) {
      setError("Select both a file and a bundle ZIP.");
      return;
    }
    setError("");
    setVerifyMessage("");
    setVerifyResult(null);
    setVerifying(true);
    try {
      const result = await post<VerificationApiResponse>("/pki/verify", {
        bundle_b64: b64e(await verifyBundle.arrayBuffer()),
        document_b64: b64e(await verifyFile.arrayBuffer()),
      });
      const normalized = normalizeVerificationResult(result);
      setVerifyResult(normalized);
      setVerifyMessage(
        normalized.verified
          ? "Server verification succeeded."
          : normalized.message || "Server verification failed."
      );
    } catch (e) {
      setVerifyMessage("");
      if (e instanceof APIError) {
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "Verification failed");
      }
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div>
      <PageHeader title="Documents" description="Digitally sign files and send signature bundles for server verification." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}
      {verifyMessage && !error && (
        <div className="mb-4">
          <Alert type={verifyResult?.verified ? "success" : "info"}>{verifyMessage}</Alert>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 font-medium text-slate-900">Sign Document</h2>
          <div className="space-y-3">
            <input
              type="file"
              className="input-field"
              onChange={(e) => {
                setError("");
                setVerifyMessage("");
                setVerifyResult(null);
                setSignFile(e.target.files?.[0] ?? null);
              }}
            />
            <input
              type="password"
              className="input-field"
              placeholder="Keystore password (if not from login)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button onClick={exportBundle} disabled={!signFile || signing}>
              {signing ? "Exporting bundle..." : "Export Signature Bundle (ZIP)"}
            </Button>
            <p className="text-xs text-slate-500">
              Bundle contents: manifest, detached signature, signer certificate.
            </p>
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 font-medium text-slate-900">Verify Document</h2>
          <div className="space-y-3">
            <div>
              <label className="label">Original File</label>
              <input
                type="file"
                className="input-field"
                onChange={(e) => {
                  setError("");
                  setVerifyMessage("");
                  setVerifyResult(null);
                  setVerifyFile(e.target.files?.[0] ?? null);
                }}
              />
            </div>
            <div>
              <label className="label">Bundle ZIP</label>
              <input
                type="file"
                accept=".zip"
                className="input-field"
                onChange={(e) => {
                  setError("");
                  setVerifyMessage("");
                  setVerifyResult(null);
                  setVerifyBundle(e.target.files?.[0] ?? null);
                }}
              />
            </div>
            <Button onClick={verify} disabled={!verifyFile || !verifyBundle || verifying}>
              {verifying ? "Verifying..." : "Verify"}
            </Button>
          </div>
        </Card>
      </div>

      {verifyResult && (
        <Card className="mt-6">
          <h2 className="mb-4 font-medium text-slate-900">
            {verifyResult.verified ? "Verification Passed" : "Verification Failed"}
          </h2>
          <div className="space-y-2 text-sm text-slate-700">
            {verifyResult.checks.map((check) => (
              <div key={check.name} className="rounded-lg border border-slate-200 px-3 py-2">
                <div className={check.ok ? "text-emerald-700" : "text-red-700"}>
                  {check.ok ? "PASS" : "FAIL"} - {check.name}
                </div>
                {check.detail && <div className="mt-1 text-slate-500">{check.detail}</div>}
              </div>
            ))}
          </div>

          {(verifyResult.signer || verifyResult.protocolVersion != null) && (
            <div className="mt-4 grid gap-3 text-sm text-slate-700 md:grid-cols-2">
              {verifyResult.signer && (
                <div className="rounded-lg border border-slate-200 px-3 py-2">
                  <div className="font-medium text-slate-900">Derived Signer</div>
                  <div>{verifyResult.signer.username || "Unknown"}</div>
                  {verifyResult.signer.serial && <div>Serial: {verifyResult.signer.serial}</div>}
                </div>
              )}
              {verifyResult.protocolVersion != null && (
                <div className="rounded-lg border border-slate-200 px-3 py-2">
                  <div className="font-medium text-slate-900">Protocol</div>
                  <div>Version: {verifyResult.protocolVersion}</div>
                </div>
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function normalizeVerificationResult(payload: VerificationApiResponse): VerificationResult {
  return {
    checks: payload.checks
      ? Object.entries(payload.checks).map(([name, check]) => ({ detail: check.detail, name, ok: check.ok }))
      : [],
    message: payload.message || payload.detail,
    protocolVersion: payload.protocol_version ?? undefined,
    signer: payload.signer_identity || payload.signer_serial
      ? {
          serial: payload.signer_serial ?? undefined,
          username: payload.signer_identity ?? undefined,
        }
      : undefined,
    verified: payload.verified === true || payload.ok === true,
  };
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
      left.localeCompare(right)
    );
    return `{${entries.map(([key, entry]) => `${JSON.stringify(key)}:${canonicalJson(entry)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function certFingerprintSha256B64(certPem: string): Promise<string> {
  const der = b64d(certPem.replace(/-----[^-]+-----/g, "").replace(/\s+/g, ""));
  return b64e(await crypto.subtle.digest("SHA-256", der));
}

function buildBundleZip(files: Record<string, Uint8Array>): Blob {
  return new Blob([zipSync(files, { level: 0 })], { type: "application/zip" });
}
