"use client";

import { AssistantLayout } from "@/components/assistant/assistant-layout";
import { useCurrentUser } from "@/components/layout/providers";
import { ProfileHandleForm } from "@/components/profile/profile-handle-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AssistantPage() {
  const { isHydrated, setUserId, userId } = useCurrentUser();

  if (!isHydrated) {
    return (
      <section className="grid min-h-[60vh] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading assistant workspace...</p>
      </section>
    );
  }

  if (!userId) {
    return (
      <div className="-mx-3 px-3 md:-mx-5 md:px-5">
        <section className="grid min-h-[70vh] place-items-center">
          <Card className="w-full max-w-3xl overflow-hidden">
            <CardHeader>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Assistant access
              </p>
              <CardTitle className="max-w-[14ch] text-4xl leading-none md:text-5xl">
                Pick a local profile handle to open the assistant workspace.
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-8 md:grid-cols-[1.2fr_0.8fr]">
              <p className="text-base leading-7 text-muted-foreground">
                This demo keeps the entire supplement journey in one place: intake, live search, stack recommendation,
                safety review, and checkout handoff. You only need a local handle so runs stay grouped in this browser.
              </p>
              <div className="rounded-[1.6rem] border border-border bg-background/70 p-5">
                <ProfileHandleForm
                  onSubmit={(nextUserId) => setUserId(nextUserId)}
                  submitLabel="Enter the assistant"
                />
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    );
  }

  return (
    <div className="-mx-3 px-3 md:-mx-5 md:px-5">
      <AssistantLayout userId={userId} />
    </div>
  );
}
