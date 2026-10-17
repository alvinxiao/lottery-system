"use strict";
const test = require("node:test"),
  assert = require("node:assert/strict"),
  crypto = require("node:crypto"),
  fs = require("node:fs"),
  vm = require("node:vm"),
  path = require("node:path"),
  os = require("node:os"),
  cp = require("node:child_process");
const C = require("../src/Core");
const hash = (v) =>
  crypto
    .createHash("sha256")
    .update(Array.isArray(v) ? Buffer.from(v) : v, "utf8")
    .digest("hex");
const at = "2026-01-01T12:00:00.000Z",
  later = (h) => new Date(Date.parse(at) + h * C.HOUR).toISOString();
function prepared() {
  const s = C.create(
    {
      event_id: "DEMO",
      admins: ["a@example.invalid", "b@example.invalid"],
      game_target: 1,
      food_target: 1,
      initial_deadline: later(1),
      grace_hours: 48,
      exception_approvers: ["a@example.invalid", "b@example.invalid"],
      publication_approvers: ["a@example.invalid", "b@example.invalid"],
    },
    [
      { class_id: "A", display_name: "Class A" },
      { class_id: "B", display_name: "Class B" },
    ],
  );
  for (const [i, c] of s.classes.entries()) {
    C.verifyContact(
      s,
      "a@example.invalid",
      c.class_id,
      c.class_id.toLowerCase() + "@example.invalid",
      "Roster officer checked",
      at,
    );
    const p = [1, 2, 3].map((r) => ({
      name: c.class_id + " booth " + r,
      description: "Safe activity " + r,
      category: i ? "food" : "game",
    }));
    const id = C.intake(
      s,
      { class_id: c.class_id, email: c.verified_email, proposals: p },
      at,
    );
    C.review(
      s,
      "a@example.invalid",
      id,
      p.map((p, j) => ({
        status: "APPROVED",
        reason: "Safety and duplicates checked",
        booth_id: c.class_id + (j + 1),
        name: p.name,
        category: p.category,
      })),
      at,
    );
  }
  return s;
}
function frozen() {
  const s = prepared();
  C.signoff(s, "a@example.invalid", at, hash);
  C.signoff(s, "b@example.invalid", at, hash);
  return s;
}
function bundle(s) {
  const assignments = s.snapshot.classes.map((c) => {
    const p = s.snapshot.proposals.find(
      (p) => p.class_id === c.class_id && p.rank === 1,
    );
    return {
      class_id: p.class_id,
      booth_id: p.booth_id,
      category: p.category,
      assigned_rank: 1,
    };
  });
  const a = {
    schema_version: 1,
    record_type: "committed_run",
    run_id: "run-1",
    event_id: s.config.event_id,
    input_hash: s.snapshot.input_hash,
    assignments,
    priority_order: s.classes.map((c) => c.class_id),
    method: "manual",
    seed: null,
    objective_vector: [2, 2, 0, -1, -1],
    committed_at: at,
    approvals: s.snapshot.config.approval_ids,
    algorithm_version: "sha256-counter-fisher-yates-v1",
    solver_version: "test",
    app_version: "test",
    status: "OPTIMAL",
    replacement: null,
    operator_approvals: [],
  };
  a.output_hash = hash(C.json(a));
  const files = Object.fromEntries(
    Object.entries(s.snapshot.files).map(([k, v]) => ["snapshot/" + k, v]),
  );
  files["assignments.csv"] = C.csv(
    ["run_id", "class_id", "booth_id", "category", "assigned_rank"],
    assignments.map((x) => ({ run_id: a.run_id, ...x })),
  );
  files["feasibility_report.json"] = C.json({
    schema_version: 1,
    run_id: a.run_id,
    input_hash: a.input_hash,
    output_hash: a.output_hash,
    feasible: true,
    status: "OPTIMAL",
    objective_vector: a.objective_vector,
  });
  files["lottery_summary.txt"] =
    `Official lottery ${a.run_id}\nEvent: ${a.event_id}\nInput SHA-256: ${a.input_hash}\nOutput SHA-256: ${a.output_hash}\nStatus: OPTIMAL\nClasses assigned: ${assignments.length}\n`;
  a.hash_manifest = Object.fromEntries(
    Object.entries(files).map(([k, v]) => [k, hash(v)]),
  );
  a.input_snapshot = {
    classes: s.snapshot.classes,
    proposals: s.snapshot.proposals,
    config: Object.fromEntries(
      Object.entries(s.snapshot.config).filter(([k]) => k !== "hash_manifest"),
    ),
  };
  files["lottery_audit.json"] = C.json(a);
  return files;
}
function imported() {
  const s = frozen();
  C.importRun(s, "a@example.invalid", bundle(s), at, hash);
  return s;
}
function send(s, id, digest = "digest-" + id) {
  const m = C.prepareMail(s, id, "assignment", at, digest);
  C.completeMail(s, m.key, { message_id: "actual-" + id }, at);
  return digest;
}
test("duplicate versions never become extra classes and explicit authority supersedes old version", () => {
  const s = prepared();
  const original = s.submissions[0];
  const id = C.intake(s, original.raw, at);
  assert.equal(s.submissions.at(-1).duplicate, true);
  assert.equal(
    s.submissions.filter(
      (x) => x.class_id === "A" && x.status === "AUTHORITATIVE",
    ).length,
    1,
  );
  C.review(s, "b@example.invalid", id, original.decisions, at);
  assert.equal(original.status, "SUPERSEDED");
  assert.equal(s.reviews.length, 3);
});
test("unverified contact, officer, missing approval and duplicate canonical IDs block freeze", () => {
  const s = prepared();
  assert.throws(() =>
    C.verifyContact(
      s,
      "officer@example.invalid",
      "A",
      "x@example.invalid",
      "proof",
      at,
    ),
  );
  s.submissions[0].raw.email = "imposter@example.invalid";
  assert.throws(() =>
    C.review(s, "a@example.invalid", "S1", s.submissions[0].decisions, at),
  );
  s.submissions[0].decisions[1].booth_id = "A1";
  assert.throws(() => C.signoff(s, "a@example.invalid", at, hash));
  assert.throws(() => C.signoff(s, "b@example.invalid", at, hash));
});
test("freeze requires distinct identities and changed input invalidates signoffs", () => {
  const s = prepared();
  C.signoff(s, "a@example.invalid", at, hash);
  assert.throws(() => C.signoff(s, "a@example.invalid", at, hash));
  s.config.food_target = 0;
  assert.throws(() => C.signoff(s, "b@example.invalid", at, hash));
});
test("correction deadlines preserve rejected versions and similarity is advisory only", () => {
  const s = prepared();
  const before = JSON.stringify(s.booths);
  const suggestions = C.suggestions(s, "S1");
  assert.ok(suggestions.every((x) => x.advisory_only));
  assert.equal(JSON.stringify(s.booths), before);
  C.correction(
    s,
    "a@example.invalid",
    "A",
    "Replace unsafe proposal",
    later(2),
    at,
  );
  assert.throws(() => C.intake(s, s.submissions[0].raw, later(3)));
  assert.equal(s.submissions.length, 2);
  assert.equal(C.missing(s, later(50)).length, 0);
});
test("uniform grace and unresolved missing classes prevent freeze", () => {
  const s = prepared();
  s.submissions = s.submissions.filter((x) => x.class_id !== "B");
  assert.equal(C.missing(s, later(2))[0].status, "GRACE");
  assert.equal(C.missing(s, later(50))[0].status, "PTA_REVIEW");
  assert.throws(() => C.signoff(s, "a@example.invalid", at, hash));
  assert.throws(() => C.signoff(s, "b@example.invalid", at, hash));
});
test("official import idempotency and every output hash bound", () => {
  const s = frozen(),
    files = bundle(s);
  assert.equal(C.importRun(s, "a@example.invalid", files, at, hash), true);
  assert.equal(C.importRun(s, "a@example.invalid", files, at, hash), false);
  for (const key of Object.keys(files)) {
    const bad = { ...files, [key]: files[key] + "x" };
    assert.throws(
      () => C.importRun(s, "a@example.invalid", bad, at, hash),
      key,
    );
  }
});
test("tampered audit with recomputed output hash still cannot invent quota/choices", () => {
  const s = frozen(),
    files = bundle(s),
    a = JSON.parse(files["lottery_audit.json"]);
  a.assignments[0].booth_id = "UNAPPROVED";
  const core = Object.fromEntries(
    Object.entries(a).filter(
      ([k]) => !["output_hash", "hash_manifest", "input_snapshot"].includes(k),
    ),
  );
  a.output_hash = hash(C.json(core));
  files["lottery_audit.json"] = C.json(a);
  assert.throws(() => C.importRun(s, "a@example.invalid", files, at, hash));
});
test("private mail actual send deadline, dry-run and uncertain-send retry ledger", () => {
  const s = imported(),
    m = C.prepareMail(s, "A", "assignment", at, "d");
  assert.equal(m.to, "a@example.invalid");
  assert.equal(C.prepareMail(s, "A", "assignment", at, "again"), null);
  C.completeMail(s, m.key, { dry_run: true }, at);
  assert.equal(s.notifications[m.key].sent_at, undefined);
  assert.equal(s.tokens.d.expires, undefined);
  const d = send(s, "B");
  assert.equal(s.tokens[d].expires, later(48));
  assert.deepEqual(C.tick(s, later(24)), [{ class_id: "B", kind: "reminder" }]);
  assert.throws(() =>
    C.respond(s, d, "a@example.invalid", "accept", later(25)),
  );
});
test("explicit accept, replay denial, autoaccept and late-decline exception", () => {
  const s = imported(),
    a = send(s, "A"),
    b = send(s, "B");
  assert.equal(
    C.respond(s, a, "a@example.invalid", "accept", later(1)),
    "CONFIRMED",
  );
  assert.throws(() =>
    C.respond(s, a, "a@example.invalid", "decline", later(2)),
  );
  C.tick(s, later(48));
  assert.equal(s.confirmations.B.status, "AUTO_ACCEPTED");
  assert.equal(
    C.respond(s, b, "b@example.invalid", "decline", later(49)),
    "PTA_REVIEW",
  );
  assert.equal(s.confirmations.B.status, "AUTO_ACCEPTED");
  assert.equal(s.exceptions[0].type, "LATE_DECLINE");
  assert.throws(() => C.publication(s, "a@example.invalid", later(50)));
});
test("decline resolution requires configured authority and affected verified consent", () => {
  const s = imported();
  send(s, "A");
  const b = send(s, "B");
  C.respond(s, b, "b@example.invalid", "decline", later(1));
  const x = s.exceptions[0],
    p = {
      reason: "Class consents to original assignment after clarification",
      roster: s.roster,
    };
  assert.throws(() =>
    C.resolveException(s, "a@example.invalid", x.id, p, later(2)),
  );
  assert.throws(() =>
    C.consent(s, x.id, "a@example.invalid", "B", "B1", later(2)),
  );
  C.consent(s, x.id, "b@example.invalid", "B", "B1", later(2));
  C.resolveException(s, "a@example.invalid", x.id, p, later(2));
  assert.equal(x.status, "OPEN");
  C.resolveException(s, "b@example.invalid", x.id, p, later(2));
  assert.equal(x.status, "RESOLVED");
  assert.equal(s.run.assignments[1].booth_id, "B1");
});
test("publication separate approvers and sanitizer output exact public columns", () => {
  const s = imported();
  send(s, "A");
  send(s, "B");
  C.tick(s, later(48));
  assert.equal(
    C.publication(s, "a@example.invalid", later(50)).status,
    "PENDING",
  );
  const p = C.publication(s, "b@example.invalid", later(50));
  assert.equal(p.status, "APPROVED");
  assert.deepEqual(Object.keys(p.entries[0]).sort(), [
    "booth_id",
    "category",
    "class_id",
  ]);
  assert.throws(() => C.publication(s, "officer@example.invalid", later(50)));
  s.config.publication_approvers = null;
  assert.throws(() => C.publication(s, "a@example.invalid", later(50)));
});
test("22-class supplied sample runs actual intake/review/freeze, and Python loads canonical exported bytes", () => {
  const demo = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, "../../sample-data/google-intake.json"),
      "utf8",
    ),
  );
  const s = C.create(
    demo.config,
    demo.classes.map((c) => ({
      class_id: c.class_id,
      display_name: c.display_name,
    })),
  );
  for (const raw of demo.submissions) {
    C.verifyContact(
      s,
      demo.config.admins[0],
      raw.class_id,
      raw.email,
      "Synthetic verification fixture",
      at,
    );
    const id = C.intake(s, raw, at);
    C.review(
      s,
      demo.config.admins[0],
      id,
      demo.review_decisions[raw.class_id],
      at,
    );
  }
  C.signoff(s, demo.config.admins[0], at, hash);
  C.signoff(s, demo.config.admins[1], at, hash);
  assert.equal(s.snapshot.proposals.length, 66);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "google-snapshot-"));
  try {
    for (const [name, text] of Object.entries(s.snapshot.files))
      fs.writeFileSync(path.join(tmp, name), text);
    const root = path.join(__dirname, "../.."),
      python = process.platform === "win32"
        ? path.join(root, ".venv", "Scripts", "python.exe")
        : path.join(root, ".venv", "bin", "python");
    if (!fs.existsSync(python))
      throw new Error("Install Python environment first for contract test");
    const p = cp.spawnSync(
      python,
      [
        "-c",
        "from lottery.snapshot import load_snapshot; import sys; s=load_snapshot(sys.argv[1]); assert len(s.classes)==22; print(s.input_hash)",
        tmp,
      ],
      { encoding: "utf8" },
    );
    assert.equal(p.status, 0, p.stderr);
    assert.equal(p.stdout.trim(), s.snapshot.input_hash);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
function adapter(s, options = {}) {
  let state = C.json(s),
    email = "a@example.invalid",
    sends = 0,
    lockHeld = false;
  const properties = {
    STATE_FILE_ID: "state",
    PRIVATE_WORKBOOK_ID: "book",
    DRY_RUN: options.live ? "false" : "true",
  };
  const sheet = {
    clearContents() {},
    getRange() {
      return { setValues() {} };
    },
    setFrozenRows() {},
  };
  const ctx = {
    LotteryCore: C,
    console,
    Date,
    Session: { getActiveUser: () => ({ getEmail: () => email }) },
    PropertiesService: {
      getScriptProperties: () => ({
        getProperty: (k) => properties[k],
        setProperty: (k, v) => (properties[k] = v),
      }),
    },
    LockService: {
      getScriptLock: () => ({
        waitLock() {
          assert.equal(lockHeld, false);
          lockHeld = true;
        },
        releaseLock() {
          lockHeld = false;
        },
      }),
    },
    DriveApp: {
      getFileById: () => ({
        getBlob: () => ({ getDataAsString: () => state }),
        setContent: (v) => {
          state = v;
        },
      }),
    },
    SpreadsheetApp: { openById: () => ({ getSheetByName: () => sheet }) },
    Utilities: {
      DigestAlgorithm: { SHA_256: "sha" },
      Charset: { UTF_8: "utf8" },
      computeDigest: (_, v) =>
        [
          ...crypto
            .createHash("sha256")
            .update(
              Array.isArray(v) ? Buffer.from(v.map((x) => (x + 256) % 256)) : v,
            )
            .digest(),
        ].map((x) => (x > 127 ? x - 256 : x)),
      getUuid: () => crypto.randomUUID(),
      base64EncodeWebSafe: (v) => Buffer.from(v).toString("base64url"),
    },
    ScriptApp: {
      getService: () => ({
        getUrl: () => "https://script.example.invalid/exec",
      }),
    },
    Gmail: {
      Users: {
        Messages: {
          send() {
            sends++;
            assert.equal(
              JSON.parse(state).notifications["run-1:A:assignment"].status,
              "SENDING",
            );
            if (options.fail) throw new Error("quota/network");
            return { id: "gmail-receipt" };
          },
        },
      },
    },
    HtmlService: { createHtmlOutput: (x) => x },
    UrlFetchApp: {
      fetch: () => ({
        getResponseCode: () => 200,
        getContentText: () =>
          JSON.stringify({
            aud: "client",
            iss: "https://accounts.google.com",
            email_verified: true,
            email: "a@example.invalid",
            exp: Date.now() / 1000 + 3600,
          }),
      }),
    },
  };
  vm.createContext(ctx);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "../src/App.js"), "utf8"),
    ctx,
  );
  return {
    context: ctx,
    app: ctx.LotteryApp,
    state: () => JSON.parse(state),
    email: (v) => (email = v),
    sends: () => sends,
  };
}
test("real adapter denies officers/blank Session, dryrun never mails or timestamps", () => {
  const a = adapter(imported());
  a.email("officer@example.invalid");
  assert.throws(() => a.app.sendAssignment("A"));
  a.email("");
  assert.throws(() => a.app.sendAssignment("A"));
  a.email("a@example.invalid");
  const preview = a.app.sendAssignment("A");
  assert.equal(preview.dry_run, true);
  assert.equal(a.sends(), 0);
  assert.equal(
    a.state().notifications["run-1:A:assignment"].sent_at,
    undefined,
  );
  assert.ok(!preview.body.includes("B1"));
});
test("real adapter persists send intent first and uncertain failure blocks duplicate until reconciled", () => {
  const a = adapter(imported(), { live: true, fail: true });
  assert.throws(() => a.app.sendAssignment("A"), /uncertain/);
  assert.equal(a.state().notifications["run-1:A:assignment"].status, "SENDING");
  a.app.sendAssignment("A");
  assert.equal(a.sends(), 1);
  a.app.reconcile("run-1:A:assignment", {
    sent: false,
    evidence: "Checked sender Sent and no message exists",
  });
  assert.equal(a.state().notifications["run-1:A:assignment"], undefined);
});
test("real adapter Gmail receipt gives actual sent timestamp and read-only GET escapes token", () => {
  const a = adapter(imported(), { live: true });
  a.app.sendAssignment("A");
  const m = a.state().notifications["run-1:A:assignment"];
  assert.equal(m.message_id, "gmail-receipt");
  assert.equal(Date.parse(m.deadline_at) - Date.parse(m.sent_at), 48 * C.HOUR);
  const before = JSON.stringify(a.state()),
    html = a.app.get({ parameter: { token: '"><script>alert(1)</script>' } });
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("A1"));
  assert.equal(JSON.stringify(a.state()), before);
});
test("real adapter verifies external Google identity and rejects missing credential/replay", () => {
  const s = imported();
  s.config.identity_client_id = "client";
  const token = "secret";
  send(s, "A", hash(token));
  s.tokens[hash(token)].expires = new Date(Date.now() + 3600000).toISOString();
  const a = adapter(s);
  assert.match(
    a.app.post({ parameter: { token, response: "accept" } }),
    /rejected/,
  );
  assert.match(
    a.app.post({
      parameter: { token, response: "accept", credential: "verified-id-token" },
    }),
    /CONFIRMED/,
  );
  assert.match(
    a.app.post({
      parameter: { token, response: "accept", credential: "verified-id-token" },
    }),
    /rejected/,
  );
});
test("published versions increase when a changed roster returns to previous assignments", () => {
  const s = imported();
  send(s, "A");
  send(s, "B");
  C.tick(s, later(48));
  C.publication(s, "a@example.invalid", later(49));
  const p = s.publications[0];
  p.status = "PUBLISHED";
  C.publication(s, "b@example.invalid", later(49));
  assert.equal(p.status, "PUBLISHED");
  s.roster[0].booth_id = "A2";
  assert.equal(C.publication(s, "a@example.invalid", later(50)).version, 2);
  s.roster[0].booth_id = "A1";
  assert.equal(C.publication(s, "a@example.invalid", later(51)).version, 3);
});
test("real adapter publication retries same prepared Sheet after PDF failure and shares only sanitized files read-only", () => {
  const s = imported();
  send(s, "A");
  send(s, "B");
  C.tick(s, later(48));
  s.config.publication_approvers = ["a@example.invalid"];
  s.config.publication_audience = { viewers: ["parent@example.invalid"] };
  const a = adapter(s),
    ctx = a.context;
  let books = 0,
    pdfFailures = 1,
    rows = [],
    shared = [];
  const sheet = {
    clearContents() {},
    getRange(r, c, n, m) {
      return {
        setValues(v) {
          rows.push(...v);
        },
      };
    },
    setFrozenRows() {},
  };
  const book = {
    getId: () => "public-sheet",
    getUrl: () => "https://sheets.example.invalid/public",
    getSheets: () => [sheet],
  };
  ctx.SpreadsheetApp.create = () => {
    books++;
    return book;
  };
  ctx.SpreadsheetApp.openById = () => book;
  ctx.SpreadsheetApp.flush = () => {};
  ctx.ScriptApp.getOAuthToken = () => "fake-oauth";
  ctx.UrlFetchApp.fetch = (url) => {
    assert.match(url, /size=letter/);
    if (pdfFailures-- > 0) return { getResponseCode: () => 503 };
    return {
      getResponseCode: () => 200,
      getBlob: () => ({ setName: () => ({}) }),
    };
  };
  ctx.DriveApp.createFile = () => ({ getId: () => "public-pdf" });
  const stateFile = ctx.DriveApp.getFileById;
  ctx.DriveApp.getFileById = (id) =>
    id === "state"
      ? stateFile(id)
      : {
          addViewers(viewers) {
            shared.push([id, ...viewers]);
          },
        };
  assert.throws(() => a.app.publish(), /PDF export failed/);
  assert.equal(a.state().publications[0].sheet_id, "public-sheet");
  assert.equal(a.state().publications[0].status, "APPROVED");
  assert.equal(a.app.publish().status, "PUBLISHED");
  assert.equal(books, 1);
  assert.deepEqual(shared.map((x) => x[0]).sort(), [
    "public-pdf",
    "public-sheet",
  ]);
  assert.deepEqual(Array.from(rows[0]), ["class", "booth", "category"]);
  assert.ok(!JSON.stringify(rows).includes("@example.invalid"));
  assert.equal(a.app.publish().status, "PUBLISHED");
  assert.equal(books, 1);
});
test("reset rehearsal sends preserves live and uncertain tokens", () => {
  const s = imported();
  send(s, "A", "live-token");
  const m = C.prepareMail(s, "B", "assignment", at, "dry-token");
  C.completeMail(s, m.key, { dry_run: true }, at);
  s.tokens["uncertain-token"] = {
    notification_key: "pending-other",
    used: false,
  };
  s.notifications["pending-other"] = { status: "SENDING" };
  const a = adapter(s);
  a.app.resetDryRuns();
  assert.ok(a.state().tokens["live-token"]);
  assert.ok(a.state().tokens["uncertain-token"]);
  assert.equal(a.state().tokens["dry-token"], undefined);
  assert.equal(a.state().notifications["run-1:A:assignment"].status, "SENT");
  assert.equal(a.state().notifications["run-1:B:assignment"], undefined);
});
test("duplicate prior entry does not bypass uniform intake deadline", () => {
  const s = prepared();
  assert.throws(
    () => C.intake(s, s.submissions[0].raw, later(5000)),
    /deadline/,
  );
  C.correction(
    s,
    "a@example.invalid",
    "A",
    "PTA voluntary revision",
    later(6000),
    later(5000),
  );
  assert.ok(C.intake(s, s.submissions[0].raw, later(5001)));
});
test("authenticated details shows only own real absolute send deadline without consuming token", () => {
  const s = imported();
  s.config.identity_client_id = "client";
  const token = "details-secret",
    digest = hash(token);
  send(s, "A", digest);
  const deadline = new Date(Date.now() + 3600000).toISOString();
  s.notifications["run-1:A:assignment"].deadline_at = deadline;
  s.tokens[digest].expires = deadline;
  const a = adapter(s);
  const html = a.app.post({
    parameter: { token, credential: "valid-id", action: "details" },
  });
  assert.ok(html.includes(deadline));
  assert.ok(html.includes("A1"));
  assert.ok(!html.includes("B1"));
  assert.equal(a.state().tokens[digest].used, false);
  assert.equal(a.state().confirmations.A, undefined);
  assert.match(
    a.app.post({
      parameter: { token, credential: "valid-id", response: "accept" },
    }),
    /CONFIRMED/,
  );
});
test("verified identity tokens require finite expiration and correct audience", () => {
  for (const claims of [
    {
      aud: "client",
      iss: "https://accounts.google.com",
      email_verified: true,
      email: "a@example.invalid",
    },
    {
      aud: "wrong",
      iss: "https://accounts.google.com",
      email_verified: true,
      email: "a@example.invalid",
      exp: Date.now() / 1000 + 3600,
    },
  ]) {
    const s = imported();
    s.config.identity_client_id = "client";
    const token = "secret";
    send(s, "A", hash(token));
    const a = adapter(s);
    a.context.UrlFetchApp.fetch = () => ({
      getResponseCode: () => 200,
      getContentText: () => JSON.stringify(claims),
    });
    assert.match(
      a.app.post({
        parameter: { token, credential: "invalid-id", action: "details" },
      }),
      /rejected/,
    );
  }
});
test("same canonical booths cannot swap categories even when totals remain exact and classes consented", () => {
  const s = imported();
  const id = C.addException(
    s,
    "CHANGE",
    ["A", "B"],
    "Test category attack",
    "a@example.invalid",
    at,
  );
  C.consent(s, id, "a@example.invalid", "A", "A1", at);
  C.consent(s, id, "b@example.invalid", "B", "B1", at);
  const roster = s.roster.map((a) => ({
    ...a,
    category: a.category === "game" ? "food" : "game",
  }));
  assert.throws(
    () =>
      C.resolveException(
        s,
        "a@example.invalid",
        id,
        { reason: "Cannot relabel approved activities", roster },
        at,
      ),
    /Canonical booth category/,
  );
});
test("deterministic draft flow feasibility rejects14 food-only classes with13 slots before freezing", () => {
  const s = C.create(
    {
      event_id: "CAPACITY",
      admins: ["a@example.invalid", "b@example.invalid"],
      game_target: 9,
      food_target: 13,
    },
    Array.from({ length: 22 }, (_, i) => ({
      class_id: "C" + i,
      display_name: "Class " + i,
    })),
  );
  for (let i = 0; i < 22; i++) {
    const c = s.classes[i],
      category = i < 14 ? "food" : "game";
    C.verifyContact(
      s,
      "a@example.invalid",
      c.class_id,
      "parent" + i + "@example.invalid",
      "Verified synthetic roster",
      at,
    );
    const proposals = [1, 2, 3].map((rank) => ({
      name: "Activity " + i + " " + rank,
      description: "Activity description",
      category,
    }));
    const id = C.intake(
      s,
      { class_id: c.class_id, email: c.verified_email, proposals },
      at,
    );
    C.review(
      s,
      "a@example.invalid",
      id,
      proposals.map((p, j) => ({
        status: "APPROVED",
        reason: "Reviewed",
        booth_id: "B" + i + "-" + j,
        name: p.name,
        category,
      })),
      at,
    );
  }
  const before = C.json(s),
    a = C.feasibility(s),
    b = C.feasibility(s);
  assert.equal(a.feasible, false);
  assert.equal(a.matched_count, 21);
  assert.equal(a.candidate_classes.length, 22);
  assert.deepEqual(a, b);
  assert.equal(C.json(s), before);
  assert.throws(
    () => C.signoff(s, "a@example.invalid", at, hash),
    /infeasible/,
  );
  assert.equal(s.snapshot, null);
  C.correction(
    s,
    "a@example.invalid",
    "C1",
    "Consider games voluntarily",
    later(48),
    at,
  );
  assert.equal(s.corrections.length, 1);
});
