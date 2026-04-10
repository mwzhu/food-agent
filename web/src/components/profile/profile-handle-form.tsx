"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ProfileHandleFormProps = {
  initialValue?: string | null;
  onSubmit: (userId: string) => Promise<void> | void;
  submitLabel: string;
};

export function ProfileHandleForm({
  initialValue,
  onSubmit,
  submitLabel,
}: ProfileHandleFormProps) {
  const [userId, setUserId] = useState(initialValue ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedUserId = userId.trim();

    if (!normalizedUserId) {
      setErrorMessage("Choose a profile handle before continuing.");
      return;
    }

    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      await onSubmit(normalizedUserId);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not save the profile handle.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form className="space-y-3" onSubmit={submit}>
      <div className="space-y-2">
        <Label htmlFor="profile-handle">Profile handle</Label>
        <Input
          id="profile-handle"
          onChange={(event) => setUserId(event.target.value)}
          placeholder="michael"
          value={userId}
        />
        <p className="text-xs leading-5 text-muted-foreground">
          Stored locally in this browser so supplement runs have a stable user id.
        </p>
      </div>

      {errorMessage ? <p className="text-sm font-medium text-accent-foreground">{errorMessage}</p> : null}

      <Button disabled={isSubmitting} type="submit">
        {isSubmitting ? "Saving..." : submitLabel}
      </Button>
    </form>
  );
}
