import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import ApprovalDialog from "../components/ApprovalDialog";
import Composer from "../components/Composer";
import MessageList from "../components/MessageList";
import { useHarness } from "../store/session";

export default function ChatPage() {
  const [params] = useSearchParams();
  const wanted = params.get("thread");
  const thread = useHarness((s) => s.thread);
  const items = useHarness((s) => s.items);
  const busy = useHarness((s) => s.busy);
  const workspace = useHarness((s) => s.workspace);
  const connected = useHarness((s) => s.connected);
  const approval = useHarness((s) => s.approval);
  const resumeThread = useHarness((s) => s.resumeThread);
  const send = useHarness((s) => s.send);
  const interrupt = useHarness((s) => s.interrupt);
  const resolveApproval = useHarness((s) => s.resolveApproval);

  useEffect(() => {
    if (!connected || !wanted || wanted === thread?.thread_id) return;
    void resumeThread(wanted);
  }, [connected, wanted, thread?.thread_id, resumeThread]);

  return (
    <>
      <header>
        <div>
          <h1>{thread ? thread.title || "未命名对话" : "新对话"}</h1>
          <p>
            {thread
              ? `${thread.thread_id.slice(0, 8)} · 运行在 ${thread.workspace || workspace || "?"}`
              : "发出第一条消息时才创建，全程只走 App Server"}
          </p>
        </div>
        <div className="header-badges">
          {workspace ? (
            <span className="badge brand" title={workspace}>
              {workspace}
            </span>
          ) : (
            <span className="badge bad">未设置 workspace · 去 Settings 填写</span>
          )}
        </div>
      </header>
      <main>
        <MessageList
          items={items}
          canSuggest={connected && Boolean(workspace)}
          onSuggest={(text) => void send(text)}
        />
      </main>
      <Composer
        busy={busy}
        disabled={!connected || !workspace}
        onSend={(text) => void send(text)}
        onInterrupt={() => void interrupt()}
      />
      {approval ? <ApprovalDialog request={approval} onResolve={(d, args) => void resolveApproval(d, args)} /> : null}
    </>
  );
}
