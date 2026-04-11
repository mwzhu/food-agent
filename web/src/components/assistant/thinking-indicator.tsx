import { cn } from "@/lib/utils";

type ThinkingIndicatorProps = {
  text: string;
  className?: string;
};

export function ThinkingIndicator({ text, className }: ThinkingIndicatorProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-3 rounded-[1.35rem] border border-border/80 bg-background/80 px-4 py-3 text-sm text-muted-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.45)]",
        className,
      )}
    >
      <span className="flex items-center gap-1.5" aria-hidden="true">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="h-2.5 w-2.5 animate-bounce rounded-full bg-secondary-foreground/70"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </span>
      <span>{text}</span>
    </div>
  );
}
