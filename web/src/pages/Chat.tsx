import { useEffect, useRef, useState } from "react";
import { useAuth } from "../lib/auth";
import { getWS, type Person } from "../components/DashboardLayout";
import { get } from "../lib/api";
import {
  ChatKeys,
  newEphemeral,
  deriveSessionKey,
  encryptChat,
  decryptChat,
  certToPem,
  getCaCertFromP12,
} from "../lib/crypto";
import {
  buildSessionContext,
  createSignedChatHandshake,
  type SignedChatHandshake,
  verifyChatHandshake,
} from "../lib/chatHandshake";
import type { WSMessage } from "../lib/ws";
import { loadChatHistory, saveChatHistory, type ChatHistoryRecord } from "../lib/chatHistory";
import { PageHeader, Alert, Card } from "../components/ui";
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
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [history, setHistory] = useState<ChatHistoryRecord[]>([]);
  const historyRef = useRef<ChatHistoryRecord[]>([]);
  const [error, setError] = useState("");
  const sessions = useRef<Map<string, ChatKeys>>(new Map());
  const pending = useRef<Map<string, ChatKeys>>(new Map());
  const queuedMessages = useRef<Map<string, string[]>>(new Map());
  const seenHandshakeReplays = useRef<Set<string>>(new Set());
  const trustCache = useRef<{ caCertPem: string; revokedSerials: Set<string> } | null>(null);
  const lineId = useRef(0);
  const chatEnd = useRef<HTMLDivElement>(null);
  const conversationUsers = Array.from(new Set([...history.map((item) => item.peer), ...people.map((person) => person.username)]));

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

  const recordHistory = async (targetPeer: string, text: string, direction: ChatHistoryRecord["direction"]) => {
    if (!session?.keystore) return;
    const next = [
      ...historyRef.current,
      { id: crypto.randomUUID(), peer: targetPeer, direction, text, createdAt: new Date().toISOString() },
    ].slice(-500);
    historyRef.current = next;
    setHistory(next);
    await saveChatHistory(session.keystore, session.username, next);
  };

  const clearUnverifiedSessions = () => {
    pending.current.clear();
    queuedMessages.current.clear();
    for (const [username, keys] of sessions.current) {
      if (!keys.sessionKey) sessions.current.delete(username);
    }
  };

  const secureFailure = () => {
    clearUnverifiedSessions();
    append("Secure connection could not be verified.", "system");
  };

  const secureEstablished = (targetPeer: string) => {
    append(`Secure conversation established with ${targetPeer}.`, "system");
  };

  const loadTrust = async (keystore: { bytes: ArrayBuffer; password: string }) => {
    const caCertPem = trustCache.current?.caCertPem
      ?? certToPem(getCaCertFromP12(keystore.bytes, keystore.password));
    const revokedSerials = new Set(
      (await get<{ revoked_serials: string[] }>("/pki/crl.json")).revoked_serials
    );
    trustCache.current = { caCertPem, revokedSerials };
    return trustCache.current;
  };

  const sendEncrypted = async (targetPeer: string, text: string, ck: ChatKeys) => {
    if (!ck.sessionKey) return;
    ck.sendCounter += 1;
    const { nonceB64, ctB64 } = await encryptChat(ck.sessionKey, text);
    getWS().client?.send({
      type: "chat_msg",
      peer: targetPeer,
      session_id: ck.offerId,
      payload: { nonce_b64: nonceB64, ct_b64: ctB64, counter: ck.sendCounter },
    });
    await recordHistory(targetPeer, text, "sent");
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
    let cancelled = false;
    if (!session?.keystore) {
      historyRef.current = [];
      setHistory([]);
      return;
    }
    loadChatHistory(session.keystore, session.username).then((records) => {
      if (!cancelled) {
        historyRef.current = records;
        setHistory(records);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [session]);

  useEffect(() => {
    if (conversationUsers.length === 0) {
      setPeer("");
      return;
    }
    if (!peer || !conversationUsers.includes(peer)) {
      setPeer(conversationUsers[0]);
    }
  }, [people, history, peer]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  useEffect(() => {
    const handler = async (msg: WSMessage) => {
      const t = msg.type as string;
      if (t === "chat_offer") {
        const envelope = msg as unknown as SignedChatHandshake;
        const sender = envelope.from;
        const offerId = envelope.offer_id;
        if (!sender || !offerId || !session) return;
        const ks = getKeystore();
        if (!ks) {
          append("[!] Keystore not loaded - sign in again with your .p12 file.", "system");
          return;
        }
        try {
          const trust = await loadTrust(ks);
          const verified = verifyChatHandshake({
            envelope,
            expectedType: "chat_offer",
            expectedFrom: sender,
            expectedTo: session.username,
            caCertPem: trust.caCertPem,
            revokedSerials: trust.revokedSerials,
            seenReplayKeys: seenHandshakeReplays.current,
          });
          if (!verified.ok) {
            secureFailure();
            return;
          }
          const { privKey, pubB64 } = await newEphemeral();
          const ck: ChatKeys = { offerId, peer: sender, privKey, pubB64, sessionKey: null, sendCounter: 0, recvCounter: 0 };
          ck.sessionKey = await deriveSessionKey(
            privKey,
            envelope.eph_pub_b64,
            buildSessionContext(offerId, sender, session.username, envelope.eph_pub_b64, pubB64)
          );
          sessions.current.set(sender, ck);
          const answer = await createSignedChatHandshake(
            "chat_answer",
            session.username,
            sender,
            offerId,
            crypto.randomUUID(),
            pubB64,
            ks.bytes,
            ks.password
          );
          getWS().client?.send(answer as unknown as Record<string, unknown>);
          secureEstablished(sender);
          await flushQueued(sender, ck);
        } catch {
          secureFailure();
        }
      } else if (t === "chat_answer") {
        const envelope = msg as unknown as SignedChatHandshake;
        const sender = envelope.from;
        const offerId = envelope.offer_id;
        const ck = pending.current.get(offerId);
        if (!sender || !ck || !offerId || !session) return;
        const ks = getKeystore();
        if (!ks) {
          pending.current.delete(offerId);
          sessions.current.delete(ck.peer);
          secureFailure();
          return;
        }
        try {
          const trust = await loadTrust(ks);
          const verified = verifyChatHandshake({
            envelope,
            expectedType: "chat_answer",
            expectedFrom: ck.peer,
            expectedTo: session.username,
            caCertPem: trust.caCertPem,
            revokedSerials: trust.revokedSerials,
            seenReplayKeys: seenHandshakeReplays.current,
          });
          if (!verified.ok) {
            pending.current.delete(offerId);
            sessions.current.delete(ck.peer);
            secureFailure();
            return;
          }
          ck.sessionKey = await deriveSessionKey(
            ck.privKey,
            envelope.eph_pub_b64,
            buildSessionContext(offerId, session.username, sender, ck.pubB64, envelope.eph_pub_b64)
          );
          pending.current.delete(offerId);
          secureEstablished(sender);
          await flushQueued(sender, ck);
        } catch {
          pending.current.delete(offerId);
          sessions.current.delete(ck.peer);
          secureFailure();
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
          await recordHistory(sender, text, "received");
        } catch {
          /* ignore */
        }
      } else if (t === "error") {
        secureFailure();
      }
    };

    getWS().handlers.push(handler);
    return () => {
      getWS().handlers = getWS().handlers.filter((h) => h !== handler);
    };
  }, [session]);

  const ensureSession = async (targetPeer: string): Promise<ChatKeys> => {
    const existing = sessions.current.get(targetPeer);
    if (existing) return existing;
    if (!session) throw new Error("Not signed in.");

    const ks = getKeystore();
    if (!ks) throw new Error("Keystore not loaded. Sign in again with your .p12 file.");

    const offerId = crypto.randomUUID();
    const { privKey, pubB64 } = await newEphemeral();
    const ck: ChatKeys = { offerId, peer: targetPeer, privKey, pubB64, sessionKey: null, sendCounter: 0, recvCounter: 0 };
    pending.current.set(offerId, ck);
    sessions.current.set(targetPeer, ck);

    const offer = await createSignedChatHandshake(
      "chat_offer",
      session.username,
      targetPeer,
      offerId,
      crypto.randomUUID(),
      pubB64,
      ks.bytes,
      ks.password
    );
    getWS().client?.send(offer as unknown as Record<string, unknown>);
    append(`Starting secure conversation with ${targetPeer}...`, "system");
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

  const peerHistory = history.filter((item) => item.peer === peer);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <PageHeader title="Secure Chat" description="End-to-end encrypted messaging." />
      {error && <div className="mb-4"><Alert type="error">{error}</Alert></div>}

      <Card className="flex flex-1 overflow-hidden p-0">
        <aside className="w-64 shrink-0 overflow-y-auto border-r border-slate-200 p-3">
          <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Chats</div>
          {conversationUsers.length === 0 && <p className="px-2 text-sm text-slate-400">No conversations yet.</p>}
          {conversationUsers.map((username) => {
            const person = people.find((item) => item.username === username);
            return (
              <button
                key={username}
                onClick={() => setPeer(username)}
                className={`mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${
                  peer === username ? "bg-brand-50 text-brand-800" : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${person?.presence_state === "online" ? "bg-emerald-500" : "bg-slate-300"}`} />
                <span className="truncate">{username}</span>
              </button>
            );
          })}
        </aside>

        <div className="flex min-w-0 flex-1 flex-col p-6">
          <div className="mb-4 flex items-center gap-3 border-b border-slate-100 pb-4">
            <div className="min-w-0 flex-1 truncate font-medium text-slate-800">{peer || "Select a conversation"}</div>
          </div>

          <div className="flex-1 overflow-y-auto rounded-lg bg-slate-50 p-4">
            {peerHistory.length === 0 && lines.length === 0 && (
              <p className="text-center text-sm text-slate-400">Select a colleague and send a message to start.</p>
            )}
            {peerHistory.map((item) => (
              <div key={item.id} className={`mb-2 flex ${item.direction === "sent" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${
                  item.direction === "sent" ? "bg-brand-700 text-white" : "border border-slate-200 bg-white text-slate-800"
                }`}>
                  {item.text}
                </div>
              </div>
            ))}
            {lines.map((l) => (
              <div
                key={l.id}
                className={`mb-2 flex text-sm ${
                  l.type === "sent" ? "justify-end" : l.type === "received" ? "justify-start" : "justify-center text-slate-400 italic"
                }`}
              >
                {l.type === "system" ? l.text : (
                  <div className={`max-w-[75%] rounded-2xl px-4 py-2 ${
                    l.type === "sent" ? "bg-brand-700 text-white" : "border border-slate-200 bg-white text-slate-800"
                  }`}>{l.text}</div>
                )}
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
        </div>
      </Card>
    </div>
  );
}
