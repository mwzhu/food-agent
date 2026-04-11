"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ChatInputStatus = "idle" | "working" | "reset";

type ChatInputProps = {
  onSend: (value: string) => Promise<void> | void;
  disabled?: boolean;
  status: ChatInputStatus;
  className?: string;
};

export function ChatInput({
  onSend,
  disabled = false,
  status,
  className,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [value, setValue] = useState("");
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, [value]);

  const submit = async () => {
    const trimmedValue = value.trim();
    if (!trimmedValue || disabled || isSending) {
      return;
    }

    setIsSending(true);

    try {
      await onSend(trimmedValue);
      setValue("");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className={cn("border-t border-border/70 bg-card/70 px-4 py-4 backdrop-blur-xl md:px-5", className)}>
      <div className="rounded-[1.6rem] border border-border bg-card/80 p-3 shadow-soft">
        <div className="flex items-end gap-3">
          <textarea
            ref={textareaRef}
            className="max-h-[200px] min-h-[48px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
            disabled={disabled || isSending}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder={placeholderForStatus(status)}
            rows={1}
            value={value}
          />
          <Button
            className="shrink-0"
            disabled={disabled || isSending || !value.trim()}
            onClick={() => void submit()}
            size="sm"
            type="button"
            variant={status === "reset" ? "secondary" : "default"}
          >
            {status === "reset" ? <RotateCcw /> : <ArrowUp />}
            {labelForStatus(status, isSending)}
          </Button>
        </div>
      </div>
    </div>
  );
}

function placeholderForStatus(status: ChatInputStatus) {
  if (status === "working") {
    return "Your assistant is working...";
  }

  if (status === "reset") {
    return "Start a new stack...";
  }

  return "Tell me about your health goals...";
}

function labelForStatus(status: ChatInputStatus, isSending: boolean) {
  if (isSending) {
    return status === "reset" ? "Resetting..." : "Sending...";
  }

  return status === "reset" ? "Reset" : "Send";
}
