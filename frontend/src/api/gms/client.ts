export interface ChatMessage {
  role: "user" | "model";
  text: string;
}

export async function gmsChat(
  systemPrompt: string,
  history: ChatMessage[],
  userMessage: string,
): Promise<string> {
  const res = await fetch("/api/v1/chat/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system_prompt: systemPrompt,
      history,
      user_message: userMessage,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `GMS API ${res.status}`);
  }

  const data = await res.json();
  return data.message ?? "No response was returned.";
}
