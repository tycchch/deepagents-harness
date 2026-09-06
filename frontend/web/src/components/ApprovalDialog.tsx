import type { ApprovalDecision, ApprovalRequestParams } from "../protocol/types";

const LABELS: Record<ApprovalDecision, string> = {
  approve: "批准",
  reject: "拒绝",
  edit: "编辑后批准",
  respond: "回复",
};

type Props = {
  request: ApprovalRequestParams;
  onResolve: (decision: ApprovalDecision, editedArgs?: Record<string, unknown>) => void;
};

export default function ApprovalDialog({ request, onResolve }: Props) {
  return (
    <div className="modal-back">
      <div className="modal">
        <h2>需要审批</h2>
        <p className="hint">{request.tool}</p>
        <pre>{JSON.stringify(request.args, null, 2)}</pre>
        <div className="actions">
          {request.allowed_decisions.map((decision) => (
            <button
              key={decision}
              type="button"
              className={decision === "reject" ? "btn danger" : "btn"}
              onClick={() => {
                if (decision === "edit") {
                  const raw = window.prompt("edited args JSON", JSON.stringify(request.args));
                  if (!raw) return;
                  onResolve(decision, JSON.parse(raw) as Record<string, unknown>);
                  return;
                }
                onResolve(decision);
              }}
            >
              {LABELS[decision] ?? decision}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
