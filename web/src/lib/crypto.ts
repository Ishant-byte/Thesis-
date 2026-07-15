import forge from "node-forge";

function b64e(b: ArrayBuffer | Uint8Array): string {
  const bytes = b instanceof Uint8Array ? b : new Uint8Array(b);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

function b64d(s: string): Uint8Array {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function bytesToBinaryString(bytes: ArrayBuffer | Uint8Array): string {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = "";
  for (let i = 0; i < view.length; i++) binary += String.fromCharCode(view[i]);
  return binary;
}

export interface KeystoreHandle {
  p12Bytes: ArrayBuffer;
  password: string;
}

export function loadKeystoreFromFile(file: File): Promise<ArrayBuffer> {
  return file.arrayBuffer();
}

function getPrivateKey(p12Bytes: ArrayBuffer, password: string): forge.pki.rsa.PrivateKey {
  const der = forge.util.createBuffer(bytesToBinaryString(p12Bytes));
  const asn1 = forge.asn1.fromDer(der);
  const p12 = forge.pkcs12.pkcs12FromAsn1(asn1, password);
  const bags = p12.getBags({ bagType: forge.pki.oids.pkcs8ShroudedKeyBag });
  const keyBag = bags[forge.pki.oids.pkcs8ShroudedKeyBag]?.[0];
  if (!keyBag?.key) {
    const keyBags2 = p12.getBags({ bagType: forge.pki.oids.keyBag });
    const kb = keyBags2[forge.pki.oids.keyBag]?.[0];
    if (!kb?.key) throw new Error("Invalid keystore or wrong password.");
    return kb.key as forge.pki.rsa.PrivateKey;
  }
  return keyBag.key as forge.pki.rsa.PrivateKey;
}

function maxPssSaltLength(key: forge.pki.rsa.PrivateKey): number {
  const emLen = Math.ceil(key.n.bitLength() / 8);
  return emLen - 32 - 2; // SHA-256 digest length = 32
}

async function forgeKeyToCryptoKey(forgeKey: forge.pki.rsa.PrivateKey): Promise<CryptoKey> {
  const rsaPrivateKey = forge.pki.privateKeyToAsn1(forgeKey);
  const privateKeyInfo = forge.pki.wrapRsaPrivateKey(rsaPrivateKey);
  const pem = forge.pki.privateKeyInfoToPem(privateKeyInfo);
  const pemBody = pem.replace(/-----[^-]+-----/g, "").replace(/\s/g, "");
  const der = b64d(pemBody);
  const buf = der.buffer.slice(der.byteOffset, der.byteOffset + der.byteLength);
  return crypto.subtle.importKey(
    "pkcs8",
    buf,
    { name: "RSA-PSS", hash: "SHA-256" },
    false,
    ["sign"]
  );
}

async function signPssSha256(p12Bytes: ArrayBuffer, password: string, data: Uint8Array): Promise<string> {
  const forgeKey = getPrivateKey(p12Bytes, password);
  const cryptoKey = await forgeKeyToCryptoKey(forgeKey);
  const saltLength = maxPssSaltLength(forgeKey);
  const sig = await crypto.subtle.sign({ name: "RSA-PSS", saltLength }, cryptoKey, data);
  return b64e(sig);
}

/** RSA-PSS-SHA256 sign over UTF-8 text (login nonce). */
export async function signTextP12(p12Bytes: ArrayBuffer, password: string, text: string): Promise<string> {
  return signPssSha256(p12Bytes, password, new TextEncoder().encode(text));
}

/** RSA-PSS-SHA256 sign over raw bytes (chat offers, file hash). */
export async function signBytesP12(p12Bytes: ArrayBuffer, password: string, data: Uint8Array | ArrayBuffer): Promise<string> {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  return signPssSha256(p12Bytes, password, bytes);
}

export async function sha256File(file: File): Promise<ArrayBuffer> {
  const buf = await file.arrayBuffer();
  return crypto.subtle.digest("SHA-256", buf);
}

export async function sha256Bytes(data: ArrayBuffer): Promise<ArrayBuffer> {
  return crypto.subtle.digest("SHA-256", data);
}

export function getCertFromP12(p12Bytes: ArrayBuffer, password: string): forge.pki.Certificate {
  const der = forge.util.createBuffer(bytesToBinaryString(p12Bytes));
  const asn1 = forge.asn1.fromDer(der);
  const p12 = forge.pkcs12.pkcs12FromAsn1(asn1, password);
  const bags = p12.getBags({ bagType: forge.pki.oids.certBag });
  const cert = bags[forge.pki.oids.certBag]?.[0]?.cert;
  if (!cert) throw new Error("No certificate in keystore.");
  return cert;
}

export function certToPem(cert: forge.pki.Certificate): string {
  return forge.pki.certificateToPem(cert);
}

export function verifySignaturePem(certPem: string, digest: ArrayBuffer, signatureB64: string): boolean {
  try {
    const cert = forge.pki.certificateFromPem(certPem);
    const pub = cert.publicKey as forge.pki.rsa.PublicKey;
    const md = forge.md.sha256.create();
    md.update(forge.util.createBuffer(new Uint8Array(digest)).getBytes(), "raw");
    // Forge verify with RSASSA-PSS (salt length auto-detected from signature)
    return pub.verify(md.digest().getBytes(), forge.util.decode64(signatureB64), "RSASSA-PSS");
  } catch {
    return false;
  }
}

// --- E2E Chat (X25519 + HKDF + AES-GCM) ---

export interface ChatKeys {
  offerId: string;
  peer: string;
  privKey: CryptoKey;
  pubB64: string;
  sessionKey: CryptoKey | null;
  sendCounter: number;
  recvCounter: number;
}

export async function newEphemeral(): Promise<{ privKey: CryptoKey; pubB64: string }> {
  const kp = (await crypto.subtle.generateKey({ name: "X25519" }, true, ["deriveBits"])) as CryptoKeyPair;
  const pubRaw = await crypto.subtle.exportKey("raw", kp.publicKey);
  return { privKey: kp.privateKey, pubB64: b64e(pubRaw) };
}

export async function deriveSessionKey(
  privKey: CryptoKey,
  peerPubB64: string,
  context: string
): Promise<CryptoKey> {
  const peerPub = await crypto.subtle.importKey(
    "raw",
    b64d(peerPubB64),
    { name: "X25519" },
    false,
    []
  );
  const shared = await crypto.subtle.deriveBits(
    { name: "X25519", public: peerPub },
    privKey,
    256
  );
  const hkdfKey = await crypto.subtle.importKey("raw", shared, "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: new TextEncoder().encode(context) },
    hkdfKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}

export async function encryptChat(sessionKey: CryptoKey, plaintext: string): Promise<{ nonceB64: string; ctB64: string }> {
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce },
    sessionKey,
    new TextEncoder().encode(plaintext)
  );
  return { nonceB64: b64e(nonce), ctB64: b64e(ct) };
}

export async function decryptChat(sessionKey: CryptoKey, nonceB64: string, ctB64: string): Promise<string> {
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: b64d(nonceB64) },
    sessionKey,
    b64d(ctB64)
  );
  return new TextDecoder().decode(pt);
}

export { b64e, b64d };
