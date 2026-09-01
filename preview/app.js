const sample = `AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  PublicApi:
    Type: AWS::Serverless::HttpApi
    Properties: {}
  Worker:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: python3.12
      Handler: app.handler
      Policies:
        - Statement:
            - Effect: Allow
              Action: '*'
              Resource: '*'
      Environment:
        Variables:
          API_TOKEN: plaintext-demo-value
`;

const template = document.querySelector("#template");
const source = document.querySelector("#source");
const run = document.querySelector("#run");
const fileInput = document.querySelector("#file-input");
const empty = document.querySelector("#empty");
const report = document.querySelector("#report");
const error = document.querySelector("#error");
const status = document.querySelector("#status");
const findings = document.querySelector("#findings");

template.value = sample;

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  if (file.size > 512 * 1024) {
    showError("The selected file exceeds the 512 KiB preview limit.");
    return;
  }
  template.value = await file.text();
  source.value = file.name.slice(0, 200);
});

run.addEventListener("click", async () => {
  setBusy(true);
  try {
    const response = await fetch("/api/audit", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({template: template.value, source: source.value}),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Audit request failed.");
    renderReport(payload);
  } catch (requestError) {
    showError(requestError.message);
  } finally {
    setBusy(false);
  }
});

function setBusy(isBusy) {
  run.disabled = isBusy;
  run.firstChild.textContent = isBusy ? "Auditing… " : "Run static audit ";
  if (isBusy) {
    status.textContent = "RUNNING";
    status.className = "status running";
  }
}

function showError(message) {
  empty.classList.add("hidden");
  report.classList.add("hidden");
  error.textContent = message;
  error.classList.remove("hidden");
  status.textContent = "ERROR";
  status.className = "status fail";
}

function renderReport(data) {
  error.classList.add("hidden");
  empty.classList.add("hidden");
  report.classList.remove("hidden");
  document.querySelector("#decision").textContent = data.decision;
  document.querySelector("#score").textContent = data.score;
  document.querySelector("#count").textContent = data.finding_count;
  status.textContent = data.decision;
  status.className = `status ${data.decision === "PASS" ? "pass" : data.decision === "FAIL" ? "fail" : "notes"}`;
  findings.replaceChildren();

  if (!data.findings.length) {
    const clean = document.createElement("p");
    clean.className = "clean";
    clean.textContent = "No deterministic findings were produced by the current rubric.";
    findings.append(clean);
    return;
  }

  data.findings.forEach((item, index) => {
    const card = document.createElement("article");
    card.className = "finding";
    const top = document.createElement("div");
    top.className = "finding-top";
    const badge = document.createElement("span");
    badge.className = `severity ${item.severity.toLowerCase()}`;
    badge.textContent = item.severity;
    const rule = document.createElement("span");
    rule.className = "rule";
    rule.textContent = item.rule_id;
    top.append(badge, rule);
    const title = document.createElement("h3");
    title.textContent = `${String(index + 1).padStart(2, "0")} · ${item.title}`;
    const path = document.createElement("code");
    path.textContent = item.path;
    const detail = document.createElement("p");
    detail.textContent = item.impact;
    const remedy = document.createElement("p");
    const remedyLabel = document.createElement("strong");
    remedyLabel.textContent = "Remediation · ";
    remedy.append(remedyLabel, item.remediation);
    card.append(top, title, path, detail, remedy);
    findings.append(card);
  });
}
