/* Pure, dependency-free workflow. All mutating calls are serialized by App.js. */
var LotteryCore = (() => {
  "use strict";
  const HOUR = 3600000;
  const fail = (message) => {
    throw new Error(message);
  };
  const requireThat = (test, message) => {
    if (!test) fail(message);
  };
  const compare = (a, b) => {
    const x = Array.from(a, (c) => c.codePointAt(0)),
      y = Array.from(b, (c) => c.codePointAt(0));
    for (let i = 0; i < Math.min(x.length, y.length); i++)
      if (x[i] !== y[i]) return x[i] - y[i];
    return x.length - y.length;
  };
  const clone = (value) => JSON.parse(JSON.stringify(value));
  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (value && typeof value === "object")
      return (
        "{" +
        Object.keys(value)
          .sort(compare)
          .map((k) => JSON.stringify(k) + ":" + canonical(value[k]))
          .join(",") +
        "}"
      );
    return JSON.stringify(value);
  }
  const json = (value) => canonical(value) + "\n";
  function safe(value) {
    requireThat(
      typeof value === "string" &&
        value.trim() === value &&
        value.length &&
        !/^[=+@-]|[\x00-\x1f]/.test(value),
      "Unsafe or empty spreadsheet text",
    );
    return value;
  }
  function csv(fields, rows) {
    const quote = (v) => {
      const s = String(v);
      return /[,"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return (
      [
        fields.join(","),
        ...rows.map((row) => fields.map((k) => quote(row[k])).join(",")),
      ].join("\n") + "\n"
    );
  }
  function create(config, classes) {
    requireThat(
      config.event_id &&
        classes.length &&
        new Set(classes.map((c) => c.class_id)).size === classes.length,
      "Invalid roster",
    );
    requireThat(
      Number.isInteger(config.game_target) &&
        Number.isInteger(config.food_target) &&
        config.game_target >= 0 &&
        config.food_target >= 0 &&
        config.game_target + config.food_target === classes.length,
      "Invalid exact quotas",
    );
    requireThat(
      Array.isArray(config.admins) &&
        config.admins.length >= 2 &&
        config.admins.length <= 3 &&
        new Set(config.admins).size === config.admins.length &&
        config.admins.every(
          (email) =>
            typeof email === "string" &&
            email === email.toLowerCase() &&
            /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email),
        ),
      "Two designated admins required",
    );
    classes.forEach((c) => {
      safe(c.class_id);
      safe(c.display_name);
    });
    return {
      config: clone(config),
      classes: clone(classes),
      submissions: [],
      reviews: [],
      corrections: [],
      booths: {},
      events: [],
      snapshot: null,
      signoffs: [],
      run: null,
      notifications: {},
      tokens: {},
      confirmations: {},
      exceptions: [],
      publications: [],
      roster: null,
    };
  }
  function admin(s, actor) {
    requireThat(
      actor && s.config.admins.includes(actor),
      "Designated administrator required",
    );
  }
  function event(s, type, actor, at, data) {
    s.events.push({ type, actor, at, data: clone(data) });
  }
  function mutable(s) {
    requireThat(
      !s.snapshot,
      "Frozen input is immutable; create a new event for corrections",
    );
  }
  function intake(s, raw, at) {
    mutable(s);
    requireThat(
      s.classes.some((c) => c.class_id === raw.class_id),
      "Unknown class",
    );
    requireThat(
      raw.email && Array.isArray(raw.proposals) && raw.proposals.length === 3,
      "Contact and three choices required",
    );
    raw.proposals.forEach((p) => {
      safe(p.name);
      safe(p.description);
      requireThat(["game", "food"].includes(p.category), "Invalid category");
    });
    requireThat(
      new Set(raw.proposals.map((p) => p.name.toLowerCase())).size === 3,
      "Three distinct proposals required",
    );
    const prior = s.submissions.filter((x) => x.class_id === raw.class_id);
    const request = s.corrections.find(
      (x) => x.class_id === raw.class_id && x.status === "OPEN",
    );
    if (request)
      requireThat(
        Date.parse(at) <= Date.parse(request.deadline),
        "Correction deadline passed",
      );
    else if (s.config.initial_deadline) {
      requireThat(
        Number.isFinite(s.config.grace_hours) && s.config.grace_hours >= 0,
        "PTA must configure uniform grace duration",
      );
      requireThat(
        Date.parse(at) <=
          Date.parse(s.config.initial_deadline) + s.config.grace_hours * HOUR,
        "Submission grace deadline passed",
      );
    }
    const entry = {
      id: "S" + (s.submissions.length + 1),
      class_id: raw.class_id,
      raw: clone(raw),
      at,
      version: prior.length + 1,
      supersedes: prior.length ? prior[prior.length - 1].id : null,
      status: "UNVERIFIED",
      duplicate: prior.length > 0,
    };
    s.submissions.push(entry);
    event(s, "INTAKE", "form", at, {
      id: entry.id,
      duplicate: entry.duplicate,
    });
    return entry.id;
  }
  function suggestions(s, id) {
    const item = s.submissions.find((x) => x.id === id);
    requireThat(item, "Unknown submission");
    const norm = (t) => t.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
    return item.raw.proposals.flatMap((p, rank) =>
      Object.entries(s.booths)
        .filter(
          ([, b]) =>
            norm(b.name) === norm(p.name) ||
            norm(b.name).includes(norm(p.name)) ||
            norm(p.name).includes(norm(b.name)),
        )
        .map(([booth_id]) => ({
          rank: rank + 1,
          booth_id,
          advisory_only: true,
        })),
    );
  }
  function review(s, actor, id, decisions, at) {
    admin(s, actor);
    mutable(s);
    const entry = s.submissions.find((x) => x.id === id);
    requireThat(entry, "Unknown submission");
    const cls = s.classes.find((c) => c.class_id === entry.class_id);
    requireThat(
      cls.verified_email &&
        cls.verified_email.toLowerCase() === entry.raw.email.toLowerCase(),
      "Roster contact must be verified separately",
    );
    requireThat(decisions.length === 3, "Review all three proposals");
    decisions.forEach((d, i) => {
      requireThat(
        ["APPROVED", "REJECTED"].includes(d.status) && d.reason,
        "Decision and reason required",
      );
      if (d.status === "APPROVED") {
        safe(d.booth_id);
        safe(d.name);
        requireThat(["game", "food"].includes(d.category), "Invalid category");
        const old = s.booths[d.booth_id];
        requireThat(
          !old || old.category === d.category,
          "Canonical booth category conflict",
        );
        s.booths[d.booth_id] = { name: d.name, category: d.category };
      }
    });
    s.submissions
      .filter(
        (x) => x.class_id === entry.class_id && x.status === "AUTHORITATIVE",
      )
      .forEach((x) => {
        x.status = "SUPERSEDED";
      });
    entry.status = "AUTHORITATIVE";
    entry.decisions = clone(decisions);
    s.reviews.push({ id, actor, at, decisions: clone(decisions) });
    s.corrections
      .filter((x) => x.class_id === entry.class_id && x.status === "OPEN")
      .forEach((x) => {
        x.status = decisions.every((d) => d.status === "APPROVED")
          ? "RESOLVED"
          : "OPEN";
      });
    event(s, "REVIEW", actor, at, { id, decisions });
  }
  function verifyContact(s, actor, classId, email, evidence, at) {
    admin(s, actor);
    mutable(s);
    requireThat(
      evidence && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email),
      "Verification evidence and email required",
    );
    const c = s.classes.find((c) => c.class_id === classId);
    requireThat(c, "Unknown class");
    c.verified_email = email.toLowerCase();
    event(s, "CONTACT_VERIFIED", actor, at, { class_id: classId, evidence });
  }
  function correction(s, actor, classId, reason, deadline, at) {
    admin(s, actor);
    mutable(s);
    requireThat(
      s.classes.some((c) => c.class_id === classId) &&
        reason &&
        Date.parse(deadline) > Date.parse(at),
      "Class, reason, future correction deadline required",
    );
    const r = {
      id: "C" + (s.corrections.length + 1),
      class_id: classId,
      reason,
      deadline,
      status: "OPEN",
    };
    s.corrections.push(r);
    event(s, "CORRECTION", actor, at, r);
    return r;
  }
  function approvedData(s) {
    requireThat(
      !s.corrections.some((x) => x.status === "OPEN"),
      "Unresolved correction",
    );
    const proposals = [];
    const classes = s.classes
      .map((c) => ({ class_id: c.class_id, display_name: c.display_name }))
      .sort((a, b) => compare(a.class_id, b.class_id));
    classes.forEach((c) => {
      const entries = s.submissions.filter(
        (x) => x.class_id === c.class_id && x.status === "AUTHORITATIVE",
      );
      requireThat(
        entries.length === 1,
        "One verified authoritative entry required per class",
      );
      const e = entries[0];
      requireThat(
        s.classes.find((x) => x.class_id === c.class_id).verified_email ===
          e.raw.email.toLowerCase(),
        "Authoritative contact verification changed; review submission again",
      );
      requireThat(
        e.decisions.every((d) => d.status === "APPROVED") &&
          new Set(e.decisions.map((d) => d.booth_id)).size === 3,
        "Three approved distinct canonical booths required",
      );
      e.decisions.forEach((d, i) =>
        proposals.push({
          class_id: c.class_id,
          rank: i + 1,
          proposal_id: e.id + "P" + (i + 1),
          booth_id: d.booth_id,
          category: d.category,
        }),
      );
    });
    requireThat(
      Number.isInteger(s.config.game_target) &&
        Number.isInteger(s.config.food_target) &&
        s.config.game_target >= 0 &&
        s.config.food_target >= 0 &&
        s.config.game_target + s.config.food_target === classes.length,
      "Invalid exact quotas",
    );
    proposals.forEach((p) =>
      requireThat(
        s.booths[p.booth_id]?.category === p.category,
        "Canonical booth category mismatch",
      ),
    );
    return { classes, proposals };
  }
  function feasibility(s) {
    const { classes, proposals } = approvedData(s),
      graph = new Map();
    function edge(a, b, capacity) {
      if (!graph.has(a)) graph.set(a, []);
      if (!graph.has(b)) graph.set(b, []);
      const forward = { to: b, capacity, reverse: graph.get(b).length },
        backward = { to: a, capacity: 0, reverse: graph.get(a).length };
      graph.get(a).push(forward);
      graph.get(b).push(backward);
    }
    classes.forEach((c) => edge("SOURCE", "CLASS:" + c.class_id, 1));
    const catalog = new Map();
    proposals.forEach((p) => {
      edge("CLASS:" + p.class_id, "BOOTH:" + p.booth_id, 1);
      catalog.set(p.booth_id, p.category);
    });
    [...catalog]
      .sort(([a], [b]) => compare(a, b))
      .forEach(([id, category]) =>
        edge("BOOTH:" + id, "CATEGORY:" + category, 1),
      );
    edge("CATEGORY:game", "SINK", s.config.game_target);
    edge("CATEGORY:food", "SINK", s.config.food_target);
    let matched = 0;
    while (true) {
      const paths = new Map([["SOURCE", null]]),
        queue = ["SOURCE"];
      for (let i = 0; i < queue.length && !paths.has("SINK"); i++) {
        const node = queue[i];
        graph.get(node).forEach((e, index) => {
          if (e.capacity > 0 && !paths.has(e.to)) {
            paths.set(e.to, { node, index });
            queue.push(e.to);
          }
        });
      }
      if (!paths.has("SINK")) break;
      let node = "SINK";
      while (node !== "SOURCE") {
        const { node: parent, index } = paths.get(node),
          e = graph.get(parent)[index];
        e.capacity--;
        graph.get(node)[e.reverse].capacity++;
        node = parent;
      }
      matched++;
    }
    return {
      official: false,
      feasible: matched === classes.length,
      matched_count: matched,
      class_count: classes.length,
      game_target: s.config.game_target,
      food_target: s.config.food_target,
      candidate_classes:
        matched === classes.length ? [] : classes.map((c) => c.class_id),
      diagnostic:
        "Deterministic capacity matching; no priority or official assignment generated. All classes may voluntarily help revise an infeasible set.",
    };
  }
  function freezeFiles(s, at, hash) {
    const { classes, proposals } = approvedData(s);
    const files = {
      "classes.csv": csv(["class_id", "display_name"], classes),
      "approved_proposals.csv": csv(
        ["class_id", "rank", "proposal_id", "booth_id", "category"],
        proposals,
      ),
    };
    const config = {
      schema_version: 1,
      event_id: s.config.event_id,
      class_count: classes.length,
      game_target: s.config.game_target,
      food_target: s.config.food_target,
      snapshot_created_at: at,
      approval_ids: s.signoffs.map((x) => x.actor).sort(),
      hash_manifest: Object.fromEntries(
        Object.entries(files).map(([k, v]) => [k, hash(v)]),
      ),
    };
    files["config.json"] = json(config);
    return {
      files,
      input_hash: hash(files["config.json"]),
      classes,
      proposals,
      config,
    };
  }
  function signoff(s, actor, at, hash) {
    admin(s, actor);
    mutable(s);
    requireThat(
      !s.signoffs.some((x) => x.actor === actor),
      "Distinct reviewers required",
    );
    requireThat(
      feasibility(s).feasible,
      "Full unique allocation with exact quotas is infeasible; invite voluntary revisions before freeze",
    );
    const digest = hash(
      json({
        classes: s.classes,
        submissions: s.submissions,
        reviews: s.reviews,
        corrections: s.corrections,
        config: s.config,
      }),
    );
    requireThat(
      !s.signoffs.length || s.signoffs[0].digest === digest,
      "Input changed since signoff; clear approvals and review again",
    );
    s.signoffs.push({ actor, at, digest });
    if (s.signoffs.length >= 2) {
      s.snapshot = freezeFiles(s, at, hash);
      event(s, "FROZEN", actor, at, { input_hash: s.snapshot.input_hash });
    }
    return s.snapshot;
  }
  function clearSignoffs(s, actor, at) {
    admin(s, actor);
    mutable(s);
    s.signoffs = [];
    event(s, "SIGNOFF_RESET", actor, at, {});
  }
  function validateRoster(s, rows) {
    requireThat(
      rows.length === s.classes.length &&
        new Set(rows.map((a) => a.class_id)).size === rows.length &&
        new Set(rows.map((a) => a.booth_id)).size === rows.length,
      "Complete unique classes and booths required",
    );
    requireThat(
      s.classes.every((c) => rows.some((a) => a.class_id === c.class_id)),
      "Unknown or missing class",
    );
    requireThat(
      rows.filter((a) => a.category === "game").length ===
        s.config.game_target &&
        rows.filter((a) => a.category === "food").length ===
          s.config.food_target,
      "Exact category quotas required",
    );
    rows.forEach((a) => {
      safe(a.booth_id);
      requireThat(["game", "food"].includes(a.category), "Invalid category");
      requireThat(
        s.booths[a.booth_id] && s.booths[a.booth_id].category === a.category,
        "Canonical booth category mismatch",
      );
    });
  }
  const runFields = [
    "schema_version",
    "record_type",
    "run_id",
    "event_id",
    "input_hash",
    "assignments",
    "priority_order",
    "method",
    "seed",
    "objective_vector",
    "committed_at",
    "approvals",
    "algorithm_version",
    "solver_version",
    "app_version",
    "status",
    "replacement",
    "operator_approvals",
  ];
  function importRun(s, actor, files, at, hash) {
    admin(s, actor);
    requireThat(s.snapshot, "Frozen input required");
    const a = JSON.parse(files["lottery_audit.json"]);
    requireThat(
      canonical(Object.keys(a).sort()) ===
        canonical(
          [
            ...runFields,
            "output_hash",
            "input_snapshot",
            "hash_manifest",
          ].sort(),
        ),
      "Unknown or missing audit fields",
    );
    requireThat(
      a.algorithm_version === "sha256-counter-fisher-yates-v1",
      "Unknown algorithm version",
    );
    requireThat(
      a.schema_version === 1 &&
        a.record_type === "committed_run" &&
        a.status === "OPTIMAL" &&
        a.run_id &&
        a.event_id === s.config.event_id &&
        a.input_hash === s.snapshot.input_hash,
      "Run/snapshot mismatch",
    );
    requireThat(
      Array.isArray(a.operator_approvals) &&
        (!a.operator_approvals.length ||
          (a.operator_approvals.length >= 2 &&
            new Set(a.operator_approvals).size ===
              a.operator_approvals.length &&
            a.operator_approvals.every((x) => a.approvals.includes(x)))),
      "Invalid operator approvals",
    );
    const bound = Object.fromEntries(runFields.map((k) => [k, a[k]]));
    requireThat(hash(json(bound)) === a.output_hash, "Output hash mismatch");
    const expected = [
      "assignments.csv",
      "feasibility_report.json",
      "lottery_summary.txt",
      ...Object.keys(s.snapshot.files).map((n) => "snapshot/" + n),
    ].sort();
    requireThat(
      a.hash_manifest &&
        canonical(Object.keys(a.hash_manifest).sort()) === canonical(expected),
      "Exact output manifest required",
    );
    requireThat(
      canonical(a.input_snapshot) ===
        canonical({
          classes: s.snapshot.classes,
          proposals: s.snapshot.proposals,
          config: Object.fromEntries(
            Object.entries(s.snapshot.config).filter(
              ([k]) => k !== "hash_manifest",
            ),
          ),
        }),
      "Embedded snapshot mismatch",
    );
    for (const [path, digest] of Object.entries(a.hash_manifest)) {
      requireThat(
        Object.hasOwn(files, path) && hash(files[path]) === digest,
        "Output manifest mismatch: " + path,
      );
    }
    for (const [name, contents] of Object.entries(s.snapshot.files))
      requireThat(
        files["snapshot/" + name] === contents,
        "Frozen snapshot bytes mismatch",
      );
    requireThat(
      files["assignments.csv"] ===
        csv(
          ["run_id", "class_id", "booth_id", "category", "assigned_rank"],
          a.assignments.map((x) => ({ run_id: a.run_id, ...x })),
        ),
      "Assignment CSV differs from audit",
    );
    validateRoster(s, a.assignments);
    a.assignments.forEach((x) =>
      requireThat(
        s.snapshot.proposals.some(
          (p) =>
            p.class_id === x.class_id &&
            p.booth_id === x.booth_id &&
            p.rank === x.assigned_rank &&
            p.category === x.category,
        ),
        "Assignment not approved",
      ),
    );
    requireThat(
      a.priority_order.length === s.classes.length &&
        new Set(a.priority_order).size === s.classes.length &&
        s.classes.every((c) => a.priority_order.includes(c.class_id)),
      "Invalid priority permutation",
    );
    requireThat(
      a.approvals.length >= 2 &&
        new Set(a.approvals).size === a.approvals.length &&
        canonical(a.approvals) === canonical(s.snapshot.config.approval_ids),
      "Approval mismatch",
    );
    requireThat(files["lottery_audit.json"] === json(a), "Noncanonical audit");
    const report = {
      schema_version: 1,
      run_id: a.run_id,
      input_hash: a.input_hash,
      output_hash: a.output_hash,
      feasible: true,
      status: "OPTIMAL",
      objective_vector: a.objective_vector,
    };
    requireThat(
      files["feasibility_report.json"] === json(report),
      "Feasibility report mismatch",
    );
    requireThat(
      files["lottery_summary.txt"] ===
        `Official lottery ${a.run_id}\nEvent: ${a.event_id}\nInput SHA-256: ${a.input_hash}\nOutput SHA-256: ${a.output_hash}\nStatus: OPTIMAL\nClasses assigned: ${a.assignments.length}\n`,
      "Summary mismatch",
    );
    const unique = a.assignments.filter(
      (x) =>
        x.assigned_rank === 1 &&
        !s.snapshot.proposals.some(
          (p) => p.class_id !== x.class_id && p.booth_id === x.booth_id,
        ),
    ).length;
    const objectives = [
      unique,
      a.assignments.filter((x) => x.assigned_rank === 1).length,
      a.assignments.filter((x) => x.assigned_rank === 2).length,
      ...a.priority_order.map(
        (cid) => -a.assignments.find((x) => x.class_id === cid).assigned_rank,
      ),
    ];
    requireThat(
      canonical(objectives) === canonical(a.objective_vector),
      "Objective values mismatch",
    );
    requireThat(
      (a.method === "manual" && a.seed === null) ||
        (a.method === "automatic" && /^[a-f0-9]{64}$/.test(a.seed)),
      "Invalid randomization",
    );
    if (a.method === "automatic") {
      const order = s.classes.map((c) => c.class_id).sort(compare),
        key = a.seed.match(/../g).map((v) => parseInt(v, 16));
      let counter = 0n;
      for (let i = order.length - 1; i > 0; i--) {
        const limit = (1n << 256n) - ((1n << 256n) % BigInt(i + 1));
        let n;
        do {
          const bytes = Array.from({ length: 16 }, (_, j) =>
            Number((counter >> BigInt((15 - j) * 8)) & 255n),
          );
          counter++;
          n = BigInt("0x" + hash([...key, ...bytes]));
        } while (n >= limit);
        const j = Number(n % BigInt(i + 1));
        [order[i], order[j]] = [order[j], order[i]];
      }
      requireThat(
        canonical(order) === canonical(a.priority_order),
        "Seed priority mismatch",
      );
    }
    requireThat(
      a.replacement === null,
      "Replacement runs require a separate documented PTA exception, not import over the original",
    );
    if (s.run) {
      requireThat(
        s.run.run_id === a.run_id && s.run.output_hash === a.output_hash,
        "Official run already imported",
      );
      return false;
    }
    s.run = clone(a);
    s.roster = clone(a.assignments);
    s.roster_version = 1;
    event(s, "RUN_IMPORTED", actor, at, {
      run_id: a.run_id,
      output_hash: a.output_hash,
    });
    return true;
  }
  function prepareMail(s, classId, kind, at, tokenDigest) {
    requireThat(s.run, "Committed result required");
    const key = s.run.run_id + ":" + classId + ":" + kind;
    if (s.notifications[key]) return null;
    const c = s.classes.find((c) => c.class_id === classId);
    requireThat(c && c.verified_email, "Verified recipient required");
    const assignment = s.roster.find((a) => a.class_id === classId);
    const primary =
      s.notifications[s.run.run_id + ":" + classId + ":assignment"];
    if (kind === "reminder")
      requireThat(
        primary &&
          primary.status === "SENT" &&
          Date.parse(at) >= Date.parse(primary.sent_at) + 24 * HOUR &&
          Date.parse(at) < Date.parse(primary.deadline_at) &&
          !s.confirmations[classId],
        "Reminder not due",
      );
    const mail = {
      key,
      class_id: classId,
      kind,
      to: c.verified_email,
      status: "SENDING",
      started_at: at,
      assignment: clone(assignment),
    };
    s.notifications[key] = mail;
    if (kind === "assignment")
      s.tokens[tokenDigest] = {
        notification_key: key,
        class_id: classId,
        email: c.verified_email,
        run_id: s.run.run_id,
        used: false,
      };
    return clone(mail);
  }
  function completeMail(s, key, result, at) {
    const m = s.notifications[key];
    requireThat(m && m.status === "SENDING", "Mail not pending");
    if (result.dry_run) {
      m.status = "DRY_RUN";
      return;
    }
    requireThat(
      result.message_id && Number.isFinite(Date.parse(at)),
      "Actual send receipt required",
    );
    m.status = "SENT";
    m.sent_at = at;
    m.message_id = result.message_id;
    if (m.kind === "assignment") {
      m.deadline_at = new Date(Date.parse(at) + 48 * HOUR).toISOString();
      Object.values(s.tokens)
        .filter((t) => t.class_id === m.class_id && t.run_id === s.run.run_id)
        .forEach((t) => {
          t.expires = m.deadline_at;
        });
    }
  }
  function reconcileMail(s, actor, key, receipt, at) {
    admin(s, actor);
    const m = s.notifications[key];
    requireThat(
      m && m.status === "SENDING" && receipt.evidence,
      "Only uncertain sends can be reconciled",
    );
    if (receipt.sent) {
      completeMail(s, key, { message_id: receipt.message_id }, receipt.sent_at);
    } else {
      delete s.notifications[key];
    }
    event(s, "MAIL_RECONCILED", actor, at, { key, receipt });
  }
  function respond(s, digest, email, response, at) {
    const t = s.tokens[digest];
    requireThat(
      t &&
        !t.used &&
        email &&
        email.toLowerCase() === t.email &&
        t.run_id === s.run.run_id &&
        t.expires,
      "Invalid token or verified recipient identity",
    );
    requireThat(["accept", "decline"].includes(response), "Invalid response");
    if (Date.parse(at) >= Date.parse(t.expires)) {
      requireThat(response === "decline", "Confirmation expired");
      t.used = true;
      if (!s.confirmations[t.class_id])
        s.confirmations[t.class_id] = { status: "AUTO_ACCEPTED", at };
      addException(
        s,
        "LATE_DECLINE",
        [t.class_id],
        "Late decline after confirmation deadline",
        email,
        at,
      );
      return "PTA_REVIEW";
    }
    requireThat(!s.confirmations[t.class_id], "Response already recorded");
    t.used = true;
    s.confirmations[t.class_id] = {
      status: response === "accept" ? "CONFIRMED" : "DECLINED",
      at,
    };
    if (response === "decline")
      addException(s, "DECLINE", [t.class_id], "Timely decline", email, at);
    event(s, "RESPONSE", email, at, { class_id: t.class_id, response });
    return s.confirmations[t.class_id].status;
  }
  function tick(s, at) {
    const due = [];
    if (s.run)
      for (const c of s.classes) {
        const m =
          s.notifications[s.run.run_id + ":" + c.class_id + ":assignment"];
        if (m && m.status === "SENT" && !s.confirmations[c.class_id]) {
          if (Date.parse(at) >= Date.parse(m.deadline_at)) {
            s.confirmations[c.class_id] = { status: "AUTO_ACCEPTED", at };
            event(s, "AUTO_ACCEPTED", "scheduler", at, {
              class_id: c.class_id,
            });
          } else if (
            Date.parse(at) >= Date.parse(m.sent_at) + 24 * HOUR &&
            !s.notifications[s.run.run_id + ":" + c.class_id + ":reminder"]
          )
            due.push({ class_id: c.class_id, kind: "reminder" });
        }
      }
    return due;
  }
  function missing(s, at) {
    requireThat(
      s.config.initial_deadline &&
        Number.isFinite(s.config.grace_hours) &&
        s.config.grace_hours >= 0,
      "PTA must configure deadline and grace",
    );
    return s.classes
      .filter(
        (c) =>
          !s.submissions.some(
            (e) => e.class_id === c.class_id && e.status === "AUTHORITATIVE",
          ),
      )
      .map((c) => ({
        class_id: c.class_id,
        status:
          Date.parse(at) < Date.parse(s.config.initial_deadline)
            ? "NOT_DUE"
            : Date.parse(at) <
                Date.parse(s.config.initial_deadline) +
                  s.config.grace_hours * HOUR
              ? "GRACE"
              : "PTA_REVIEW",
        deadline: new Date(
          Date.parse(s.config.initial_deadline) + s.config.grace_hours * HOUR,
        ).toISOString(),
      }));
  }
  function addException(s, type, affected, reason, actor, at) {
    requireThat(
      reason &&
        affected.length &&
        affected.every((id) => s.classes.some((c) => c.class_id === id)),
      "Exception reason and known affected classes required",
    );
    const x = {
      id: "E" + (s.exceptions.length + 1),
      type,
      affected: clone(affected),
      reason,
      actor,
      at,
      status: "OPEN",
      history: [],
      approvals: [],
      consents: {},
    };
    s.exceptions.push(x);
    event(s, "EXCEPTION_OPEN", actor, at, x);
    return x.id;
  }
  function resolveException(s, actor, id, proposal, at) {
    admin(s, actor);
    const x = s.exceptions.find((x) => x.id === id);
    requireThat(x && x.status === "OPEN", "Open exception required");
    const policy = s.config.exception_approvers;
    requireThat(
      Array.isArray(policy) && policy.length && policy.includes(actor),
      "PTA exception approval authority is not configured",
    );
    requireThat(
      proposal.reason && Array.isArray(proposal.roster),
      "Documented resolution required",
    );
    validateRoster(s, proposal.roster);
    const changed = proposal.roster.filter((a) => {
      const old = s.roster.find((b) => b.class_id === a.class_id);
      return old.booth_id !== a.booth_id || old.category !== a.category;
    });
    changed.forEach((a) => {
      requireThat(
        x.affected.includes(a.class_id),
        "Every changed class must be affected",
      );
      requireThat(
        x.consents[a.class_id] &&
          x.consents[a.class_id].booth_id === a.booth_id &&
          x.consents[a.class_id].category === a.category,
        "Affected class consent required",
      );
    });
    x.affected.forEach((cid) =>
      requireThat(
        x.consents[cid] &&
          x.consents[cid].booth_id ===
            proposal.roster.find((a) => a.class_id === cid).booth_id,
        "Affected verified acceptance required",
      ),
    );
    const digest = canonical(proposal);
    requireThat(
      !x.proposed || x.proposed === digest,
      "Approvers must approve same resolution",
    );
    x.proposed = digest;
    if (!x.approvals.includes(actor)) x.approvals.push(actor);
    if (policy.every((a) => x.approvals.includes(a))) {
      x.status = "RESOLVED";
      x.history.push({
        actor,
        at,
        proposal: clone(proposal),
        previous_roster: clone(s.roster),
      });
      s.roster = clone(proposal.roster);
      s.roster_version = (s.roster_version || 1) + 1;
      x.roster_version = s.roster_version;
      x.affected.forEach((cid) => {
        requireThat(
          x.consents[cid] &&
            x.consents[cid].booth_id ===
              s.roster.find((a) => a.class_id === cid).booth_id,
          "Affected verified acceptance required",
        );
        s.confirmations[cid] = { status: "CONFIRMED", at, exception_id: id };
      });
    }
    event(s, "EXCEPTION_APPROVAL", actor, at, { id, proposal });
  }
  function consent(s, id, email, classId, boothId, at) {
    const x = s.exceptions.find((x) => x.id === id),
      c = s.classes.find((c) => c.class_id === classId);
    requireThat(
      x &&
        x.status === "OPEN" &&
        x.affected.includes(classId) &&
        c &&
        email &&
        c.verified_email === email.toLowerCase(),
      "Affected verified recipient required",
    );
    requireThat(s.booths[boothId], "Approved canonical booth required");
    x.consents[classId] = {
      booth_id: boothId,
      category: s.booths[boothId].category,
      email,
      at,
    };
    event(s, "CONSENT", email, at, { id, classId, boothId });
  }
  function publication(s, actor, at) {
    admin(s, actor);
    requireThat(s.run, "Committed result required");
    validateRoster(s, s.roster);
    requireThat(
      s.classes.every(
        (c) =>
          s.confirmations[c.class_id] &&
          ["CONFIRMED", "AUTO_ACCEPTED"].includes(
            s.confirmations[c.class_id].status,
          ),
      ) && !s.exceptions.some((x) => x.status !== "RESOLVED"),
      "Unresolved confirmations or exceptions",
    );
    requireThat(
      Array.isArray(s.config.publication_approvers) &&
        s.config.publication_approvers.length &&
        s.config.publication_approvers.includes(actor),
      "PTA publication approval authority is not configured",
    );
    const entries = s.roster
      .map((a) => ({
        class_id: a.class_id,
        booth_id: a.booth_id,
        category: a.category,
      }))
      .sort((a, b) => compare(a.class_id, b.class_id));
    const fingerprint = canonical(entries);
    let p = s.publications[s.publications.length - 1];
    if (p && p.fingerprint !== fingerprint) p = null;
    if (!p) {
      p = {
        version: s.publications.length + 1,
        entries,
        fingerprint,
        approvals: [],
        at,
        status: "PENDING",
      };
      s.publications.push(p);
    }
    if (!p.approvals.includes(actor)) p.approvals.push(actor);
    if (p.status !== "PUBLISHED")
      p.status = s.config.publication_approvers.every((a) =>
        p.approvals.includes(a),
      )
        ? "APPROVED"
        : "PENDING";
    event(s, "PUBLICATION_APPROVAL", actor, at, { version: p.version });
    return clone(p);
  }
  return {
    HOUR,
    canonical,
    json,
    csv,
    safe,
    create,
    admin,
    intake,
    suggestions,
    review,
    verifyContact,
    correction,
    signoff,
    clearSignoffs,
    feasibility,
    importRun,
    validateRoster,
    prepareMail,
    completeMail,
    reconcileMail,
    respond,
    tick,
    missing,
    addException,
    resolveException,
    consent,
    publication,
  };
})();
if (typeof module !== "undefined") module.exports = LotteryCore;
