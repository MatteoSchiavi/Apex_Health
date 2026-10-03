import { beforeEach, expect, mock, test } from "bun:test";
import { NextRequest } from "next/server";

let owner: any = { id: 1 };
let session: any = { id: 10, userId: 1, title: null };
let providerError = false;
let modelText = "I do not have your health readings in this conversation.";
let draftStatus = "pending";
let conflict = false;
const createMessage = mock(async ({ data }: any) => ({ id: 99, ...data, createdAt: new Date() }));
const sessionUpdate = mock(async () => ({}));
const updateDraft = mock(async ({ data }: any) => { if (!conflict) draftStatus = JSON.parse(data.drafts)[0].status; return { count: conflict ? 0 : 1 }; });
const completion = mock(async (_args: any) => {
  if (providerError) throw new Error("provider secret sk-fixture-do-not-expose");
  return { choices: [{ message: { content: modelText } }] };
});
const fakeDb = {
  user: { findFirst: async () => owner },
  chatSession: { findFirst: async ({ where }: any) => session?.id === where.id && session?.userId === where.userId ? session : null, update: sessionUpdate },
  chatMessage: {
    create: createMessage, updateMany: updateDraft,
    findMany: async ({ where }: any) => where.role === "assistant"
      ? [{ id: 90, drafts: JSON.stringify([{ id: "old-draft", status: draftStatus, kind: "supplement_protocol" }]) }]
      : [{ role: "assistant", content: "Prior response" }, { role: "user", content: "Prior question" }],
  },
  contextDoc: { findMany: async () => [{ kind: "goals", content: "Run a 10k" }, { kind: "medical", content: "" }] },
  $transaction: async (fn: any) => fn(fakeDb),
};
mock.module("../../src/lib/db", () => ({ db: fakeDb }));
mock.module("z-ai-web-dev-sdk", () => ({ default: { create: async () => ({ chat: { completions: { create: completion } } }) } }));
const { POST: send } = await import("../../src/app/api/coach/chats/[id]/messages/route");
const { POST: update } = await import("../../src/app/api/coach/chats/[id]/drafts/[draftId]/route");
const request = (body: unknown) => new NextRequest("http://localhost/api/coach", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const context = (id = "10") => ({ params: Promise.resolve({ id }) });
const draftContext = { params: Promise.resolve({ id: "10", draftId: "old-draft" }) };
beforeEach(() => {
  owner = { id: 1 }; session = { id: 10, userId: 1, title: null };
  providerError = false; conflict = false; draftStatus = "pending";
  modelText = "I do not have your health readings in this conversation.";
  createMessage.mockClear(); sessionUpdate.mockClear(); completion.mockClear(); updateDraft.mockClear();
});

test("provider failure is 502, reveals no provider secret and persists no successful reply or drafts", async () => {
  providerError = true;
  const response = await send(request({ content: "plan my workouts and iron supplements" }), context());
  expect(response.status).toBe(502);
  expect(await response.text()).not.toContain("sk-fixture");
  expect(createMessage).not.toHaveBeenCalled();
  expect(sessionUpdate).not.toHaveBeenCalled();
});
test("an empty provider response is an error, not a successful fallback", async () => {
  modelText = "";
  expect((await send(request({ content: "sleep" }), context())).status).toBe(502);
  expect(createMessage).not.toHaveBeenCalled();
});
test("reply cites only supplied documents and never synthesizes plans, supplement protocols or tool calls", async () => {
  const response = await send(request({ content: "plan my workouts and iron supplements" }), context());
  const body = await response.json();
  expect(response.status).toBe(200);
  expect(body.assistant_message.drafts).toBeNull();
  expect(body.assistant_message.referenced_data).toEqual({ tool_calls: [], context_keys: ["doc:goals"] });
  expect(createMessage.mock.calls[1][0].data.drafts).toBeNull();
  const messages = completion.mock.calls[0][0].messages;
  expect(messages[0].role).toBe("system");
  expect(messages[0].content).toContain("No health readings");
  expect(messages.filter((m: any) => m.content.includes("plan my workouts"))).toHaveLength(1);
});
test("oversized messages and malformed IDs cannot call the model", async () => {
  expect((await send(request({ content: "x".repeat(4001) }), context())).status).toBe(400);
  expect((await send(request({ content: "sleep" }), context("10suffix"))).status).toBe(400);
  expect(completion).not.toHaveBeenCalled();
});
test("foreign session cannot reach the model", async () => {
  session.userId = 2;
  expect((await send(request({ content: "sleep" }), context())).status).toBe(404);
  expect(completion).not.toHaveBeenCalled();
});
test("missing account is not implicitly created", async () => {
  owner = null;
  expect((await send(request({ content: "sleep" }), context())).status).toBe(404);
  expect(completion).not.toHaveBeenCalled();
});
test("confirm cannot report an unapplied plan or protocol as successful", async () => {
  expect((await update(request({ action: "confirm" }), draftContext)).status).toBe(501);
  expect(updateDraft).not.toHaveBeenCalled();
});
test("discard is idempotent and terminal states cannot be reversed", async () => {
  expect((await update(request({ action: "discard" }), draftContext)).status).toBe(200);
  expect((await update(request({ action: "discard" }), draftContext)).status).toBe(200);
  expect(updateDraft).toHaveBeenCalledTimes(1);
  draftStatus = "confirmed";
  expect((await update(request({ action: "discard" }), draftContext)).status).toBe(409);
});
test("concurrent draft edits cannot overwrite a newer saved value", async () => {
  conflict = true;
  expect((await update(request({ action: "discard" }), draftContext)).status).toBe(409);
});
