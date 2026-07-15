import { useEffect, useRef, useState } from "react";
import { useAuth } from "../lib/auth";
import { getWS, type Person } from "../components/DashboardLayout";
import {
  ChatKeys,
  newEphemeral,
  deriveSessionKey,
  encryptChat,
  decryptChat,
  signBytesP12,
} from "../lib/crypto";
import type { WSMessage } from "../lib/ws";
import { PageHeader, Alert, Card, Select } from "../components/ui";
import { Button } from "../components/Button";

interface ChatLine {
  id: number;
  text: string;
  type: "sent" | "received" | "system";
}
// main function
export function ChatPage() {
  const { session } = useAuth();
  const [people, setPeople] = useState<Person[]>([]);
  const [peer, setPeer] = useState("");
  const [message, setMessage] = useState("");
  const [expiry, setExpiry] = useState("Off");
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [error, setError] = useState("");
  const sessions = useRef<Map<string, ChatKeys>>(new Map());
  const pending = useRef<Map<string, ChatKeys>>(new Map());
  const queuedMessages = useRef<Map<string, string[]>>(new Map());
  const lineId = useRef(0);
  const chatEnd = useRef<HTMLDivElement>(null);

  const append = (text: string, type: ChatLine["type"] = "system") => {
    lineId.current += 1;
    setLines((prev) => [...prev, { id: lineId.current, text, type }]);
  };

  const getKeystore = (): { bytes: ArrayBuffer; password: string } | null => {
    if (session?.keystore && session.keystorePassword) {
      return { bytes: session.keystore, password: session.keystorePassword };
    }
    return null;
  };

  const expirySeconds = () => {
    if (expiry === "30s") return 30;
    if (expiry === "5m") return 300;
    if (expiry === "1h") return 3600;
    return 0;
  };

  const sendEncrypted = async (targetPeer: string, text: string, ck: ChatKeys) => {
    if (!ck.sessionKey) return;
    ck.sendCounter += 1;
    const { nonceB64, ctB64 } = await encryptChat(ck.sessionKey, text);
    getWS().client?.send({
      type: "chat_msg",
      peer: targetPeer,
      session_id: ck.offerId,
      payload: { nonce_b64: nonceB64, ct_b64: ctB64, counter: ck.sendCounter, expire_seconds: expirySeconds() },
    });
    append(`You -> ${targetPeer}: ${text}`, "sent");
  };

  const flushQueued = async (targetPeer: string, ck: ChatKeys) => {
    const queued = queuedMessages.current.get(targetPeer) ?? [];
    if (!queued.length || !ck.sessionKey) return;
    queuedMessages.current.delete(targetPeer);
    for (const text of queued) {
      await sendEncrypted(targetPeer, text, ck);
    }
  };

  useEffect(() => {
    const interval = setInterval(() => {
      setPeople(getWS().people.filter((p) => p.username !== session?.username));
    }, 2000);
    return () => clearInterval(interval);
  }, [session]);

  useEffect(() => {
    if (people.length === 0) {
      setPeer("");
      return;
    }
    if (!peer || !people.some((p) => p.username === peer)) {
      setPeer(people[0].username);
    }
  }, [people, peer]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  useEffect(() => {
    const handler = async (msg: WSMessage) => {
      const t = msg.type as string;
      if (t === "chat_offer") {
        const sender = msg.from as string;
        const offerId = msg.offer_id as string;
        const ephPubB64 = msg.eph_pub_b64 as string;
        if (!sender || !offerId || !ephPubB64 || !session) return;
        const ks = getKeystore();
        if (!ks) {
          append("[!] Keystore not loaded - sign in again with your .p12 file.", "system");
          return;
        }
        try {
          const { privKey, pubB64 } = await newEphemeral();
          const ck: ChatKeys = { offerId, peer: sender, privKey, pubB64, sessionKey: null, sendCounter: 0, recvCounter: 0 };
          ck.sessionKey = await deriveSessionKey(privKey, ephPubB64, offerId);
          sessions.current.set(sender, ck);
          const data = new TextEncoder().encode(`chat_answer|${sender}|${session.username}|${offerId}|${pubB64}`);
          const sigB64 = await signBytesP12(ks.bytes, ks.password, data);
          getWS().client?.send({ type: "chat_answer", offer_id: offerId, eph_pub_b64: pubB64, sig_b64: sigB64 });
          append(`Secure session accepted: ${sender}`, "system");
          await flushQueued(sender, ck);
        } catch (e) {
          append(`Failed to accept session: ${e instanceof Error ? e.message : "error"}`, "system");
        }
      } else if (t === "chat_answer") {
        const sender = msg.from as string;
        const offerId = msg.offer_id as string;
        const ephPubB64 = msg.eph_pub_b64 as string;
        const ck = pending.current.get(offerId);
        if (!sender || !ck || !ephPubB64) return;
        try {
          ck.sessionKey = await deriveSessionKey(ck.privKey, ephPubB64, offerId);
          pending.current.delete(offerId);
          append(`Secure session established with ${sender}`, "system");
          await flushQueued(sender, ck);
        } catch {
          /* ignore */
        }
      } else if (t === "chat_msg") {
        const sender = msg.from as string;
        const sessionId = msg.session_id as string;
        const payload = msg.payload as { nonce_b64: string; ct_b64: string; counter: number };
        const ck = sessions.current.get(sender);
        if (!ck || ck.offerId !== sessionId || !ck.sessionKey) return;
        if (payload.counter <= ck.recvCounter) return;
        ck.recvCounter = payload.counter;
        try {
          const text = await decryptChat(ck.sessionKey, payload.nonce_b64, payload.ct_b64);
          append(`${sender}: ${text}`, "received");
        } catch {
          /* ignore */
        }
      } else if (t === "error") {
        append(`[server] ${msg.message}`, "system");
      }
    };

    getWS().handlers.push(handler);
    return () => {
      getWS().handlers = getWS().handlers.filter((h) => h !== handler);
    };
  }, [expiry, session]);

  const ensureSession = async (targetPeer: string): Promise<ChatKeys> => {
    const existing = sessions.current.get(targetPeer);
    if (existing) return existing;

    const ks = getKeystore();
    if (!ks) throw new Error("Keystore not loaded. Sign in again with your .p12 file.");

    const offerId = crypto.randomUUID().slice(0, 12);
    const { privKey, pubB64 } = await newEphemeral();
    const ck: ChatKeys = { offerId, peer: targetPeer, privKey, pubB64, sessionKey: null, sendCounter: 0, recvCounter: 0 };
    pending.current.set(offerId, ck);
    sessions.current.set(targetPeer, ck);

    const data = new TextEncoder().encode(`chat_offer|${session!.username}|${targetPeer}|${offerId}|${pubB64}`);
    const sigB64 = await signBytesP12(ks.bytes, ks.password, data);
    getWS().client?.send({ type: "chat_offer", peer: targetPeer, offer_id: offerId, eph_pub_b64: pubB64, sig_b64: sigB64 });
    append(`Starting secure session with ${targetPeer}...`, "system");
    return ck;
  };

  const send = async () => {
    const text = message.trim();
    if (!peer || !text || !session) return;
    setError("");
    try {
      const ck = await ensureSession(peer);
      if (!ck.sessionKey) {
        const queued = queuedMessages.current.get(peer) ?? [];
        queued.push(text);
        queuedMessages.current.set(peer, queued);
        setMessage("");
        append("Waiting for peer to accept session...", "system");
        return;
      }
      await sendEncrypted(peer, text, ck);
      setMessage("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Send failed");
    }
  };

  const peerOptions = people.map((p) => p.username);
  const peerSelectOptions = peerOptions.length ? peerOptions : [{ value: "", label: "No peers online" }];

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <PageHeader title="Secure Chat" description="End-to-end encrypted messaging with optional disappearing messages." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}

      <Card className="flex flex-1 flex-col overflow-hidden">
        <div className="mb-4 flex flex-wrap items-center gap-3 border-b border-slate-100 pb-4">
          <Select
            label=""
            value={peer}
            onChange={setPeer}
            options={peerSelectOptions}
          />
          <Select label="" value={expiry} onChange={setExpiry} options={["Off", "30s", "5m", "1h"]} />
        </div>

        <div className="flex-1 overflow-y-auto rounded-lg bg-slate-50 p-4">
          {lines.length === 0 && (
            <p className="text-center text-sm text-slate-400">Select a colleague and send a message to start.</p>
          )}
          {lines.map((l) => (
            <div
              key={l.id}
              className={`mb-2 text-sm ${
                l.type === "sent" ? "text-brand-800" : l.type === "received" ? "text-slate-800" : "text-slate-400 italic"
              }`}
            >
              {l.text}
            </div>
          ))}
          <div ref={chatEnd} />
        </div>

        <div className="mt-4 flex gap-3">
          <input
            className="input-field flex-1"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Type a message..."
          />
          <Button onClick={send} disabled={!peer || !message.trim()}>Send</Button>
        </div>
      </Card>
    </div>
  );
}
