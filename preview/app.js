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
const runOracle = document.querySelector("#run-oracle");
const oracleStatus = document.querySelector("#oracle-status");
const oracleResult = document.querySelector("#oracle-result");
const oracleError = document.querySelector("#oracle-error");
const oracleCases = document.querySelector("#oracle-cases");
const runDemo = document.querySelector("#run-demo");
const apiState = document.querySelector("#api-state");
const fixtureCount = document.querySelector("#fixture-count");
const activity = document.querySelector("#activity");
const auditFlow = document.querySelector("#audit-flow");
let demoRunning = false;

template.value = sample;
initializePreview();

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

run.addEventListener("click", runAudit);
runOracle.addEventListener("click", runOracleSuite);
runDemo.addEventListener("click", runPortfolioDemo);

async function initializePreview() {
  try {
    const response = await fetch("/api/health", {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok || payload.status !== "ok") throw new Error(payload.error || "Health check failed.");
    apiState.textContent = "CONNECTED";
    apiState.className = "connected";
    fixtureCount.textContent = String(payload.oracle_case_count);
    activity.textContent = "Service connected. The supplied sample is ready for a deterministic review.";
    syncDemoButton();
  } catch (requestError) {
    apiState.textContent = "OFFLINE";
    apiState.className = "offline";
    activity.textContent = "Preview API unavailable. Run `make preview-start`, then refresh this page.";
  }
}

async function runAudit() {
  setBusy(true);
  auditFlow.dataset.state = "running";
  activity.textContent = "Submitting the template as data to the deterministic audit engine…";
  try {
    const response = await fetch("/api/audit", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({template: template.value, source: source.value}),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Audit request failed.");
    renderReport(payload);
    auditFlow.dataset.state = "complete";
    activity.textContent = `Audit complete: ${payload.decision}, score ${payload.score}/100, ${payload.finding_count} findings.`;
    return true;
  } catch (requestError) {
    showError(requestError.message);
    auditFlow.dataset.state = "error";
    activity.textContent = `Audit failed: ${requestError.message}`;
    return false;
  } finally {
    setBusy(false);
  }
}

async function runOracleSuite() {
  setOracleBusy(true);
  activity.textContent = `Comparing ${fixtureCount.textContent} audit fixtures with repository-owned expectations…`;
  try {
    const response = await fetch("/api/oracle/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: "{}",
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Oracle request failed.");
    renderOracleSuite(payload);
    activity.textContent = `Oracle ${payload.verdict}: ${payload.matched_count}/${payload.case_count} cases matched expected evidence.`;
    return true;
  } catch (requestError) {
    oracleResult.classList.add("hidden");
    oracleError.textContent = requestError.message;
    oracleError.classList.remove("hidden");
    oracleStatus.textContent = "ERROR";
    oracleStatus.className = "status fail";
    activity.textContent = `Oracle failed: ${requestError.message}`;
    return false;
  } finally {
    setOracleBusy(false);
  }
}

async function runPortfolioDemo() {
  demoRunning = true;
  syncDemoButton();
  template.value = sample;
  source.value = "portfolio-demo.yaml";
  const audited = await runAudit();
  if (audited) await runOracleSuite();
  document.querySelector("#results-heading").scrollIntoView({behavior: "smooth", block: "start"});
  demoRunning = false;
  syncDemoButton();
}

function setBusy(isBusy) {
  run.disabled = isBusy;
  syncDemoButton();
  run.firstChild.textContent = isBusy ? "Auditing… " : "Run static audit ";
  if (isBusy) {
    status.textContent = "RUNNING";
    status.className = "status running";
  }
}

function setOracleBusy(isBusy) {
  runOracle.disabled = isBusy;
  syncDemoButton();
  runOracle.firstChild.textContent = isBusy ? "Comparing… " : "Run oracle suite ";
  if (isBusy) {
    oracleStatus.textContent = "RUNNING";
    oracleStatus.className = "status running";
  }
}

function syncDemoButton() {
  runDemo.disabled = demoRunning || run.disabled || runOracle.disabled || apiState.textContent !== "CONNECTED";
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

function renderOracleSuite(data) {
  oracleError.classList.add("hidden");
  oracleResult.classList.remove("hidden");
  document.querySelector("#oracle-verdict").textContent = data.verdict;
  document.querySelector("#oracle-matched").textContent = data.matched_count;
  document.querySelector("#oracle-total").textContent = data.case_count;
  oracleStatus.textContent = data.verdict;
  oracleStatus.className = `status ${data.verdict === "MATCH" ? "pass" : "fail"}`;
  oracleCases.replaceChildren();

  data.cases.forEach((item) => {
    const card = document.createElement("article");
    card.className = `oracle-case ${item.oracle.verdict === "MATCH" ? "matched" : "mismatched"}`;

    const top = document.createElement("div");
    top.className = "oracle-case-top";
    const caseId = document.createElement("code");
    caseId.textContent = item.case_id;
    const verdict = document.createElement("span");
    verdict.className = `status ${item.oracle.verdict === "MATCH" ? "pass" : "fail"}`;
    verdict.textContent = item.oracle.verdict;
    top.append(caseId, verdict);

    const title = document.createElement("h3");
    title.textContent = item.title;
    const summary = document.createElement("p");
    summary.textContent = `Audit decision ${item.report.decision} · ${item.oracle.summary.matched}/${item.oracle.summary.total} oracle checks matched`;

    const checks = document.createElement("ul");
    checks.className = "oracle-checks";
    item.oracle.checks.forEach((check) => {
      const row = document.createElement("li");
      const mark = document.createElement("span");
      mark.textContent = check.status === "MATCH" ? "✓" : "×";
      mark.className = check.status === "MATCH" ? "check-match" : "check-mismatch";
      const label = document.createElement("span");
      label.textContent = check.check_id.replaceAll("_", " ");
      row.append(mark, label);
      checks.append(row);
    });

    const provenance = document.createElement("p");
    provenance.className = "oracle-provenance";
    provenance.textContent = `manifest sha256 · ${item.manifest_sha256.slice(0, 16)}…`;

    const inspect = document.createElement("button");
    inspect.type = "button";
    inspect.className = "inspect-button";
    inspect.textContent = "Inspect audit findings";
    inspect.addEventListener("click", () => {
      renderReport(item.report);
      document.querySelector("#results-heading").scrollIntoView({behavior: "smooth", block: "start"});
    });

    card.append(top, title, summary, checks, provenance, inspect);
    oracleCases.append(card);
  });
  oracleStatus.focus();
}
