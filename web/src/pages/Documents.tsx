import { useState } from "react";
import { useAuth } from "../lib/auth";
import { get, health } from "../lib/api";
import {
  sha256File,
  signBytesP12,
  getCertFromP12,
  certToPem,
  verifySignaturePem,
  b64e,
  b64d,
} from "../lib/crypto";
import { PageHeader, Alert, Card } from "../components/ui";
import { Button } from "../components/Button";

interface Bundle {
  v: number;
  alg: string;
  hash_alg: string;
  file_name: string;
  sha256_b64: string;
  signature_b64: string;
  cert_pem: string;
  ca_cert_pem: string;
  meta: { signed_by?: string; cert_serial?: string; timestamp_utc?: string };
}

export function DocumentsPage() {
  const { session } = useAuth();
  const [signFile, setSignFile] = useState<File | null>(null);
  const [verifyFile, setVerifyFile] = useState<File | null>(null);
  const [verifyBundle, setVerifyBundle] = useState<File | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const log = (s: string) => setLogs((prev) => [...prev, s]);

  const getKeystore = (): ArrayBuffer | null => session?.keystore ?? null;

  const exportBundle = async () => {
    if (!signFile || !session) return;
    setError("");
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
    try {
      const ca = await get<{ ca_cert_pem: string }>("/pki/ca.pem");
      const crl = await get<{ revoked_serials: string[] }>("/pki/crl.json");
      const digest = await sha256File(signFile);
      const sigB64 = await signBytesP12(ks, pw, new Uint8Array(digest));
      const cert = getCertFromP12(ks, pw);
      const h = await health();
      const bundle: Bundle = {
        v: 1,
        alg: "RSA-PSS-SHA256",
        hash_alg: "SHA256",
        file_name: signFile.name,
        sha256_b64: b64e(digest),
        signature_b64: sigB64,
        cert_pem: certToPem(cert),
        ca_cert_pem: ca.ca_cert_pem,
        meta: {
          signed_by: session.username,
          cert_serial: cert.serialNumber,
          timestamp_utc: h.time,
        },
      };

      const zip = await buildZip(bundle, digest, sigB64);
      const url = URL.createObjectURL(zip);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${signFile.name}.signature.zip`;
      a.click();
      URL.revokeObjectURL(url);
      log(`[sign] Bundle exported for ${signFile.name}`);
      log(`[sign] Revoked check skipped at export (${crl.revoked_serials.length} entries in CRL)`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Signing failed");
    }
  };

  const buildZip = async (bundle: Bundle, digest: ArrayBuffer, sigB64: string): Promise<Blob> => {
    const files: Record<string, Uint8Array> = {
      "bundle.json": new TextEncoder().encode(JSON.stringify(bundle, null, 2)),
      "document.sha256": new Uint8Array(digest),
      "signature.sig": b64d(sigB64),
      "signer_cert.pem": new TextEncoder().encode(bundle.cert_pem),
      "ca_cert.pem": new TextEncoder().encode(bundle.ca_cert_pem),
    };
    return createSimpleZip(files);
  };

  const verify = async () => {
    if (!verifyFile || !verifyBundle) {
      setError("Select both a file and a bundle ZIP.");
      return;
    }
    setError("");
    try {
      const caServer = await get<{ ca_cert_pem: string }>("/pki/ca.pem");
      const crl = await get<{ revoked_serials: string[] }>("/pki/crl.json");
      const revoked = new Set(crl.revoked_serials.map(String));

      const bundleJson = await readZipEntry(verifyBundle, "bundle.json");
      const bundle = JSON.parse(bundleJson) as Bundle;
      const digest = await sha256File(verifyFile);
      if (b64e(digest) !== bundle.sha256_b64) {
        log("[FAIL] Hash mismatch. The file has changed or wrong file selected.");
        return;
      }
      if (bundle.ca_cert_pem.trim() !== caServer.ca_cert_pem.trim()) {
        log("[FAIL] CA certificate mismatch (CA pinning failed).");
        return;
      }
      const serialMatch = bundle.meta.cert_serial ?? "";
      if (revoked.has(String(serialMatch))) {
        log("[FAIL] Certificate is revoked (CRL).");
        return;
      }
      const ok = verifySignaturePem(bundle.cert_pem, digest, bundle.signature_b64);
      if (!ok) {
        log("[FAIL] Signature invalid.");
        return;
      }
      log("[OK] Signature verified.");
      log(`     Signed by: ${bundle.meta.signed_by ?? "unknown"}`);
      log(`     Serial: ${bundle.meta.cert_serial ?? "unknown"}`);
      log(`     Algorithms: ${bundle.alg} + ${bundle.hash_alg}`);
    } catch (e) {
      log(`[FAIL] Verification error: ${e instanceof Error ? e.message : "unknown"}`);
    }
  };

  return (
    <div>
      <PageHeader title="Documents" description="Digitally sign files and verify signature bundles." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 font-medium text-slate-900">Sign Document</h2>
          <div className="space-y-3">
            <input type="file" className="input-field" onChange={(e) => setSignFile(e.target.files?.[0] ?? null)} />
            <input
              type="password"
              className="input-field"
              placeholder="Keystore password (if not from login)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button onClick={exportBundle} disabled={!signFile}>Export Signature Bundle (ZIP)</Button>
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 font-medium text-slate-900">Verify Document</h2>
          <div className="space-y-3">
            <div>
              <label className="label">Original File</label>
              <input type="file" className="input-field" onChange={(e) => setVerifyFile(e.target.files?.[0] ?? null)} />
            </div>
            <div>
              <label className="label">Bundle ZIP</label>
              <input type="file" accept=".zip" className="input-field" onChange={(e) => setVerifyBundle(e.target.files?.[0] ?? null)} />
            </div>
            <Button onClick={verify}>Verify</Button>
          </div>
        </Card>
      </div>

      {logs.length > 0 && (
        <Card className="mt-6">
          <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-slate-700">
            {logs.join("\n")}
          </pre>
        </Card>
      )}
    </div>
  );
}

/** Minimal ZIP writer (store only, no compression) for bundle export. */
function createSimpleZip(files: Record<string, Uint8Array>): Blob {
  const parts: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;

  for (const [name, data] of Object.entries(files)) {
    const nameBytes = new TextEncoder().encode(name);
    const header = new Uint8Array(30 + nameBytes.length);
    const view = new DataView(header.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(8, 0, true);
    view.setUint16(26, nameBytes.length, true);
    view.setUint32(18, data.length, true);
    header.set(nameBytes, 30);
    parts.push(header, data);

    const cd = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(cd.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(16, data.length, true);
    cv.setUint32(20, data.length, true);
    cv.setUint32(42, offset, true);
    cd.set(nameBytes, 46);
    central.push(cd);
    offset += header.length + data.length;
  }

  const centralStart = offset;
  let centralSize = 0;
  for (const c of central) {
    parts.push(c);
    centralSize += c.length;
  }

  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, central.length, true);
  ev.setUint16(10, central.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, centralStart, true);
  parts.push(end);

  const total = parts.reduce((s, p) => s + p.length, 0);
  const out = new Uint8Array(total);
  let pos = 0;
  for (const p of parts) {
    out.set(p, pos);
    pos += p.length;
  }
  return new Blob([out], { type: "application/zip" });
}

async function readZipEntry(zipFile: File, entryName: string): Promise<string> {
  const buf = await zipFile.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let i = 0;
  while (i < bytes.length - 30) {
    const sig = new DataView(bytes.buffer, i, 4).getUint32(0, true);
    if (sig !== 0x04034b50) break;
    const compMethod = new DataView(bytes.buffer, i + 8, 2).getUint16(0, true);
    const compSize = new DataView(bytes.buffer, i + 18, 4).getUint32(0, true);
    const nameLen = new DataView(bytes.buffer, i + 26, 2).getUint16(0, true);
    const extraLen = new DataView(bytes.buffer, i + 28, 2).getUint16(0, true);
    const name = new TextDecoder().decode(bytes.slice(i + 30, i + 30 + nameLen));
    const dataStart = i + 30 + nameLen + extraLen;
    if (name === entryName) {
      const data = bytes.slice(dataStart, dataStart + compSize);
      if (compMethod !== 0) throw new Error("Compressed ZIP entries not supported");
      return new TextDecoder().decode(data);
    }
    i = dataStart + compSize;
  }
  throw new Error(`Entry ${entryName} not found in ZIP`);
}
