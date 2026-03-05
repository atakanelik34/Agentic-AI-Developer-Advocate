import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send } from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  provider?: string;
  model?: string;
  tokens?: number;
}

type JobTrigger = {
  key: string;
  label: string;
  endpoint: string;
  payload: Record<string, unknown>;
};

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";
const HEALTH_POLL_MS = 15000;
const TRIGGERS: JobTrigger[] = [
  { key: "content", label: "Run Content", endpoint: "/webhook/trigger-content", payload: {} },
  { key: "community", label: "Run Community", endpoint: "/webhook/trigger-community", payload: { limit: 25 } },
  { key: "feedback", label: "Run Feedback", endpoint: "/webhook/trigger-feedback", payload: {} },
  { key: "report", label: "Run Report", endpoint: "/webhook/trigger-report", payload: {} },
];

const formatTime = () => {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
};

const ChatInterface = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [healthState, setHealthState] = useState<"ok" | "degraded" | "fail" | "unknown">("unknown");
  const [activeTrigger, setActiveTrigger] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; retryPayload: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    let mounted = true;

    const refreshHealth = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`);
        if (!res.ok) throw new Error("health failed");
        const data = (await res.json()) as { status?: "ok" | "degraded" | "fail" };
        if (mounted) {
          setHealthState(data.status || "unknown");
        }
      } catch {
        if (mounted) setHealthState("fail");
      }
    };

    void refreshHealth();
    const timer = setInterval(() => {
      void refreshHealth();
    }, HEALTH_POLL_MS);

    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  const sendMessage = async (text: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: formatTime(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, workload: "standard" }),
      });

      if (!res.ok) throw new Error("Request failed");

      const data = await res.json();
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.reply || data.response || "No response.",
        timestamp: formatTime(),
        provider: data.provider,
        model: data.model,
        tokens: (data.input_tokens || 0) + (data.output_tokens || 0) || data.tokens,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setError({ message: "CONNECTION LOST", retryPayload: text });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && !isLoading) sendMessage(input.trim());
    }
  };

  const handleRetry = () => {
    if (error?.retryPayload) {
      sendMessage(error.retryPayload);
    }
  };

  const triggerWorkflow = async (trigger: JobTrigger) => {
    setActiveTrigger(trigger.key);
    try {
      const res = await fetch(`${BACKEND_URL}${trigger.endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(trigger.payload),
      });
      if (!res.ok) throw new Error("trigger failed");
      const data = (await res.json()) as { job_id?: string };
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `${trigger.label} queued${data.job_id ? ` (job_id: ${data.job_id})` : ""}.`,
        timestamp: formatTime(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Failed to queue ${trigger.label}. Check backend URL and logs.`,
        timestamp: formatTime(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } finally {
      setActiveTrigger(null);
    }
  };

  return (
    <div className="relative z-10 flex flex-col h-screen max-w-[720px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-primary/20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-secondary border border-primary/40 flex items-center justify-center text-primary text-xs font-bold">
            K
          </div>
          <span className="text-primary text-sm tracking-[0.3em] font-bold">KAIROS</span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${healthState === "ok" ? "bg-primary animate-pulse-glow" : "bg-destructive"}`} />
          <span className="text-muted-foreground text-xs tracking-wider">
            {healthState === "ok" ? "ONLINE" : healthState.toUpperCase()}
          </span>
        </div>
      </header>

      <section className="px-4 pt-3 shrink-0">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {TRIGGERS.map((trigger) => (
            <button
              key={trigger.key}
              onClick={() => void triggerWorkflow(trigger)}
              disabled={activeTrigger !== null}
              className="border border-border rounded px-2 py-1.5 text-[11px] uppercase tracking-wider text-primary hover:bg-secondary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {activeTrigger === trigger.key ? "Queued..." : trigger.label}
            </button>
          ))}
        </div>
      </section>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <p className="text-muted-foreground text-sm text-center opacity-50">
              [ AWAITING INPUT ]
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`animate-fade-in-up flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={
                msg.role === "user"
                  ? "bg-secondary border border-primary/30 rounded-lg px-4 py-2.5 max-w-[85%]"
                  : "max-w-[85%]"
              }
            >
              <p className="text-primary text-sm whitespace-pre-wrap leading-relaxed">
                {msg.content}
              </p>
            </div>
            <div className="flex items-center gap-2 mt-1.5">
              <span className="text-muted-foreground text-[10px]">{msg.timestamp}</span>
              {msg.role === "assistant" && msg.provider && (
                <span className="text-muted-foreground/50 text-[10px]">
                  {msg.provider} · {msg.model} · {msg.tokens} tokens
                </span>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="animate-fade-in-up flex flex-col items-start">
            <p className="text-primary text-sm">
              [ KAIROS IS THINKING
              <span className="animate-blink">...</span> ]
            </p>
          </div>
        )}

        {error && (
          <div className="animate-fade-in-up flex flex-col items-start">
            <button
              onClick={handleRetry}
              className="text-destructive text-sm hover:text-destructive/80 transition-colors cursor-pointer"
            >
              [ {error.message} — RETRY? ]
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {/* Input */}
      <footer className="px-4 pb-4 pt-2 shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter message..."
            rows={1}
            className="flex-1 bg-background border border-border rounded px-3 py-2.5 text-primary text-sm placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/60 resize-none transition-colors"
          />
          <button
            onClick={() => input.trim() && !isLoading && sendMessage(input.trim())}
            disabled={!input.trim() || isLoading}
            className="px-3 py-2.5 border border-border rounded text-primary text-sm hover:bg-secondary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-center text-muted-foreground/30 text-[10px] mt-3 tracking-wider">
          KairosAgent · Autonomous AI Agent · @KairosAgentX
        </p>
      </footer>
    </div>
  );
};

export default ChatInterface;
