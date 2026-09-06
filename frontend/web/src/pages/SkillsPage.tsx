import { useEffect, useState } from "react";
import { useHarness } from "../store/session";

export default function SkillsPage() {
  const skills = useHarness((s) => s.skills);
  const connected = useHarness((s) => s.connected);
  const refreshSkills = useHarness((s) => s.refreshSkills);
  const readSkill = useHarness((s) => s.readSkill);
  const writeSkill = useHarness((s) => s.writeSkill);
  const [path, setPath] = useState("");
  const [content, setContent] = useState("");
  const selected = skills.find((s) => s.path === path);
  const editable = selected?.scope === "personal";

  useEffect(() => {
    if (connected) void refreshSkills();
  }, [connected, refreshSkills]);

  return (
    <>
      <header>
        <div>
          <h1>Skills</h1>
          <p>公共只读；个人可写 /skills/personal/**</p>
        </div>
        {editable ? (
          <button type="button" className="btn" onClick={() => void writeSkill(path, content)}>
            保存
          </button>
        ) : null}
      </header>
      <main>
        <div className="list">
          {skills.map((skill) => (
            <button
              key={skill.path}
              type="button"
              className="row"
              onClick={() => {
                setPath(skill.path);
                void readSkill(skill.path).then(setContent);
              }}
            >
              <span>
                {skill.name} · {skill.scope}
              </span>
              <span className="hint">{skill.path}</span>
            </button>
          ))}
        </div>
        {path ? (
          <div className="field" style={{ marginTop: 16, maxWidth: "100%" }}>
            <label>{path}</label>
            <textarea
              rows={18}
              value={content}
              readOnly={!editable}
              onChange={(e) => setContent(e.target.value)}
            />
          </div>
        ) : (
          <p className="hint">点一条 skill 查看 SKILL.md</p>
        )}
      </main>
    </>
  );
}
