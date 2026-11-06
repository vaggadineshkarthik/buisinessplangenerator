"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ChatView } from "@/components/chat/chat-view";
import { LoadingState } from "@/components/shared/states";

function ChatPageInner() {
  const params = useSearchParams();
  return (
    <ChatView
      initialConversationId={params.get("conversation")}
      initialQuestion={params.get("q")}
    />
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading chat…" />}>
      <ChatPageInner />
    </Suspense>
  );
}
