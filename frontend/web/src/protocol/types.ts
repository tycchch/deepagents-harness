export const PROTOCOL_VERSION = "0.1.0";

export type ClientType = "cli" | "desktop";

export type ApprovalDecision = "approve" | "edit" | "reject" | "respond";

export type ItemType =
  | "user_message"
  | "agent_message"
  | "reasoning"
  | "command_execution"
  | "file_change"
  | "tool_call"
  | "skill_use";

export type RpcRequest = {
  jsonrpc: "2.0";
  id: number | string;
  method: string;
  params?: Record<string, unknown>;
};

export type RpcNotification = {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
};

export type RpcError = {
  code: number;
  message: string;
  data?: unknown;
};

export type RpcResponse = {
  jsonrpc: "2.0";
  id: number | string;
  result?: unknown;
  error?: RpcError;
};

export type RpcMessage = RpcRequest | RpcNotification | RpcResponse;

export type InitializeParams = {
  protocol_version: string;
  client: ClientType;
  cwd: string;
};

export type InitializeResult = {
  protocol_version: string;
  server_name: string;
};

export type ThreadStartParams = {
  workspace: string;
  sandbox?: boolean;
};

export type ThreadInfo = {
  thread_id: string;
  workspace: string;
  title: string;
  updated_at: string;
  archived?: boolean;
  source?: string;
};

export type ThreadResumeParams = {
  thread_id: string;
};

export type TurnStartParams = {
  thread_id: string;
  text: string;
};

export type TurnInterruptParams = {
  thread_id: string;
};

export type SkillInfo = {
  name: string;
  scope: "shared" | "personal";
  path: string;
};

export type ItemEvent = {
  item_id: string;
  type: ItemType;
  text?: string | null;
  tool?: string | null;
  path?: string | null;
};

export type ApprovalRequestParams = {
  request_id: string;
  tool: string;
  args: Record<string, unknown>;
  allowed_decisions: ApprovalDecision[];
};

export type ApprovalResolveParams = {
  request_id: string;
  decision: ApprovalDecision;
  edited_args?: Record<string, unknown> | null;
  message?: string | null;
};

export type ConfigMap = Record<string, unknown>;

export type ProviderProtocol = "anthropic" | "openai";

export type ModelItem = {
  id: string;
  label?: string;
};

export type ProviderInfo = {
  id: string;
  name: string;
  protocol: ProviderProtocol | string;
  base_url: string;
  api_key?: string;
  has_key?: boolean;
  models: ModelItem[];
  mapping: Record<string, string>;
};

export type ModelsState = {
  active_provider: string;
  active_model: string;
  providers: ProviderInfo[];
};
