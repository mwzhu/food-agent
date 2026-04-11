"use client";

import { useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  MessageSquareText,
  Plus,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type HistorySidebarProps = {
  activeLabel: string;
  onNewConversation: () => void;
};

const ARCHIVED_CONVERSATIONS = [
  { title: "Sleep & recovery", subtitle: "Apr 8" },
  { title: "Fitness stack", subtitle: "Mar 22" },
  { title: "Travel immunity", subtitle: "Mar 4" },
];

export function HistorySidebar({
  activeLabel,
  onNewConversation,
}: HistorySidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "hidden h-full shrink-0 border-r border-border/70 bg-background/35 lg:flex lg:flex-col",
        isCollapsed ? "w-[56px]" : "w-[200px]",
      )}
    >
      <div className="flex items-center justify-between gap-2 px-3 py-4">
        {!isCollapsed ? (
          <Button className="flex-1 justify-start" onClick={onNewConversation} size="sm" type="button">
            <Plus />
            New conversation
          </Button>
        ) : (
          <Button onClick={onNewConversation} size="sm" type="button">
            <Plus />
          </Button>
        )}
        <Button
          onClick={() => setIsCollapsed((current) => !current)}
          size="sm"
          type="button"
          variant="ghost"
        >
          {isCollapsed ? <ChevronRight /> : <ChevronLeft />}
        </Button>
      </div>

      <div className="flex-1 space-y-2 px-2 pb-3">
        <ConversationItem
          active
          collapsed={isCollapsed}
          subtitle="Current workspace"
          title={activeLabel}
        />
        {ARCHIVED_CONVERSATIONS.map((conversation) => (
          <ConversationItem
            key={conversation.title}
            collapsed={isCollapsed}
            subtitle={conversation.subtitle}
            title={conversation.title}
          />
        ))}
      </div>
    </aside>
  );
}

function ConversationItem({
  title,
  subtitle,
  active = false,
  collapsed,
}: {
  title: string;
  subtitle: string;
  active?: boolean;
  collapsed: boolean;
}) {
  return (
    <button
      className={cn(
        "flex w-full items-start gap-3 rounded-[1.15rem] border border-transparent px-3 py-3 text-left transition-colors hover:bg-card/70",
        active && "border-border bg-card/85 shadow-soft",
        collapsed && "justify-center px-2",
      )}
      type="button"
    >
      <MessageSquareText className={cn("mt-0.5 size-4 shrink-0", active ? "text-secondary-foreground" : "text-muted-foreground")} />
      {!collapsed ? (
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{title}</p>
          <p className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">
            {subtitle}
          </p>
        </div>
      ) : null}
    </button>
  );
}
