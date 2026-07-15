export type WSMessage = Record<string, unknown>;

type Handler = (msg: WSMessage) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private handlers: Handler[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private url: string;
  private shouldRun = false;

  constructor(url: string) {
    this.url = url;
  }

  onMessage(handler: Handler) {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  start() {
    this.shouldRun = true;
    this.connect();
  }

  private connect() {
    if (!this.shouldRun) return;
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => this.send({ type: "ping" });
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as WSMessage;
        this.handlers.forEach((h) => h(msg));
      } catch {
        /* ignore */
      }
    };
    this.ws.onclose = () => {
      if (this.shouldRun) {
        this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      }
    };
  }

  send(payload: WSMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  stop() {
    this.shouldRun = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}
