"use strict";
const C = require("../src/Core"),
  fs = require("node:fs"),
  path = require("node:path"),
  crypto = require("node:crypto");
const hash = (v) =>
  crypto
    .createHash("sha256")
    .update(Array.isArray(v) ? Buffer.from(v) : v)
    .digest("hex");
const at = "2026-01-01T12:00:00.000Z",
  time = (h) => new Date(Date.parse(at) + h * C.HOUR).toISOString();
const [command, input, second, third] = process.argv.slice(2);
function save(root, name, v) {
  fs.mkdirSync(root, { recursive: true });
  fs.writeFileSync(
    path.join(root, name),
    typeof v === "string" ? v : C.json(v),
  );
}
if (command === "prepare") {
  const d = JSON.parse(fs.readFileSync(input, "utf8")),
    s = C.create(
      d.config,
      d.classes.map((c) => ({
        class_id: c.class_id,
        display_name: c.display_name,
      })),
    );
  for (const raw of d.submissions) {
    C.verifyContact(
      s,
      d.config.admins[0],
      raw.class_id,
      raw.email,
      "SYNTHETIC rehearsal contact roster verification",
      at,
    );
    const id = C.intake(s, raw, at);
    C.review(s, d.config.admins[0], id, d.review_decisions[raw.class_id], at);
  }
  for (const actor of d.config.admins.slice(0, 2))
    C.signoff(s, actor, at, hash);
  for (const [name, text] of Object.entries(s.snapshot.files))
    save(path.join(second, "frozen"), name, text);
  save(second, "state.json", s);
  console.log(
    C.json({
      state: path.resolve(second, "state.json"),
      frozen: path.resolve(second, "frozen"),
      input_hash: s.snapshot.input_hash,
    }).trim(),
  );
} else if (command === "complete") {
  const s = JSON.parse(fs.readFileSync(input, "utf8")),
    files = {};
  function read(dir, prefix = "") {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (e.isDirectory()) read(path.join(dir, e.name), prefix + e.name + "/");
      else
        files[prefix + e.name] = fs.readFileSync(
          path.join(dir, e.name),
          "utf8",
        );
    }
  }
  read(second);
  C.importRun(s, s.config.admins[0], files, at, hash);
  C.importRun(s, s.config.admins[0], files, at, hash);
  for (const c of s.classes) {
    const m = C.prepareMail(
      s,
      c.class_id,
      "assignment",
      at,
      hash("mock-" + c.class_id),
    );
    C.completeMail(s, m.key, { message_id: "SYNTHETIC-" + c.class_id }, at);
  }
  const [first, declining] = s.classes;
  C.respond(
    s,
    hash("mock-" + first.class_id),
    first.verified_email,
    "accept",
    time(1),
  );
  C.respond(
    s,
    hash("mock-" + declining.class_id),
    declining.verified_email,
    "decline",
    time(2),
  );
  const x = s.exceptions[0],
    assignment = s.roster.find((a) => a.class_id === declining.class_id);
  C.consent(
    s,
    x.id,
    declining.verified_email,
    declining.class_id,
    assignment.booth_id,
    time(3),
  );
  const policy = s.config.exception_approvers;
  if (!Array.isArray(policy) || !policy.length)
    throw new Error(
      "Synthetic fixture must explicitly configure exception authority",
    );
  for (const actor of policy)
    C.resolveException(
      s,
      actor,
      x.id,
      {
        reason: "SYNTHETIC voluntary acceptance after clarification",
        roster: s.roster,
      },
      time(3),
    );
  C.tick(s, time(48));
  let published;
  for (const actor of s.config.publication_approvers)
    published = C.publication(s, actor, time(49));
  if (published.status !== "APPROVED") throw new Error("Publication blocked");
  save(third, "state.json", s);
  save(third, "sanitized-roster.json", {
    version: published.version,
    entries: published.entries,
  });
  save(third, "summary.json", {
    mode: "SYNTHETIC_ONLY_NO_GOOGLE_OR_MAIL",
    classes: s.classes.length,
    input_hash: s.snapshot.input_hash,
    run_id: s.run.run_id,
    explicit: s.classes.filter(
      (c) => s.confirmations[c.class_id].status === "CONFIRMED",
    ).length,
    auto_accepted: s.classes.filter(
      (c) => s.confirmations[c.class_id].status === "AUTO_ACCEPTED",
    ).length,
    exceptions_resolved: s.exceptions.filter((x) => x.status === "RESOLVED")
      .length,
    roster_version: published.version,
  });
  console.log(
    "Completed synthetic rehearsal; no Google services or mail called.",
  );
} else
  throw new Error(
    "Usage: rehearse.js prepare INTAKE_JSON OUTDIR | complete STATE_JSON EXPORT_DIR OUTDIR",
  );
