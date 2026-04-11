"use client";

import { useEffect, useRef } from "react";

import type { HealthProfile } from "@/lib/supplement-types";

import { ChatMessageBubble } from "./chat-message";
import type { ChatMessage } from "./message-types";

type ChatThreadProps = {
  messages: ChatMessage[];
  intakeInitialValues?: Partial<HealthProfile>;
  onSubmitIntake: (payload: HealthProfile) => Promise<void>;
};

export function ChatThread({
  messages,
  intakeInitialValues,
  onSubmitIntake,
}: ChatThreadProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const updateAutoScroll = () => {
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      shouldAutoScrollRef.current = distanceFromBottom < 100;
    };

    updateAutoScroll();
    container.addEventListener("scroll", updateAutoScroll);

    return () => container.removeEventListener("scroll", updateAutoScroll);
  }, []);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }

    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto overscroll-contain px-4 py-5 md:px-5"
    >
      <div className="space-y-4">
        {messages.map((message) => (
          <ChatMessageBubble
            key={message.id}
            intakeInitialValues={intakeInitialValues}
            message={message}
            onSubmitIntake={onSubmitIntake}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
