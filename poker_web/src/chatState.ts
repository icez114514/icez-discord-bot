export type ChatMessage = { id: string; sequence: number; author: { id: string; display_name: string }; created_at: number; text: string; client_message_id: string };
export type ChatUpdate = { type: 'chat'; table_id: string; messages: ChatMessage[]; sequence: number; closed: boolean; initial?: boolean };
export function mergeChat(previous: ChatUpdate | null, update: ChatUpdate): ChatUpdate {
  if (update.closed) return { ...update, messages: [] };
  if (!previous || previous.table_id !== update.table_id || update.initial) return update;
  const messages = new Map(previous.messages.map(m => [m.sequence, m]));
  update.messages.forEach(m => messages.set(m.sequence, m));
  return { ...update, sequence: Math.max(previous.sequence, update.sequence), messages: [...messages.values()].sort((a,b) => a.sequence-b.sequence).slice(-100) };
}
export const chatLength = (text: string) => [...text.trim()].length;
