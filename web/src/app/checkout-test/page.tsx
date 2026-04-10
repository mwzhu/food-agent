"use client";

import { BrowserUseSmokeTest } from "@/components/checkout/browser-use-smoke-test";
import { ChatgptInstacartLab } from "@/components/checkout/chatgpt-instacart-lab";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function CheckoutTestPage() {
  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Checkout lab</p>
          <CardTitle className="text-4xl md:text-5xl">Test two execution rails side by side</CardTitle>
          <CardDescription className="max-w-3xl text-base">
            The new ChatGPT Instacart path lets you test a language-driven checkout workflow without depending on
            merchant-site automation. The original Browser Use path stays here so you can compare reliability and keep
            exercising the existing approval flow.
          </CardDescription>
        </CardHeader>
      </Card>

      <Tabs defaultValue="chatgpt">
        <TabsList className="md:grid-cols-2">
          <TabsTrigger value="chatgpt">ChatGPT + Instacart</TabsTrigger>
          <TabsTrigger value="browser">Browser Use</TabsTrigger>
        </TabsList>

        <TabsContent value="chatgpt">
          <ChatgptInstacartLab />
        </TabsContent>

        <TabsContent value="browser">
          <BrowserUseSmokeTest />
        </TabsContent>
      </Tabs>
    </section>
  );
}
