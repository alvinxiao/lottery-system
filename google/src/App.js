/* Apps Script V8 adapter. Web confirmation executes as owner; external identity is verified with Google ID tokens. */
var LotteryApp = (() => {
  "use strict";
  const TABS = [
    "Classes",
    "Submissions",
    "Proposals",
    "Duplicate Review",
    "Booth Inventory",
    "Correction Requests",
    "Lottery",
    "Confirmations",
    "Exceptions",
    "Audit Log",
    "Admin Dashboard",
  ];
  const now = () => new Date().toISOString();
  const actor = () =>
    String(Session.getActiveUser().getEmail() || "").toLowerCase();
  const props = () => PropertiesService.getScriptProperties();
  const hash = (text) =>
    (Array.isArray(text)
      ? Utilities.computeDigest(
          Utilities.DigestAlgorithm.SHA_256,
          text.map((v) => (v > 127 ? v - 256 : v)),
        )
      : Utilities.computeDigest(
          Utilities.DigestAlgorithm.SHA_256,
          text,
          Utilities.Charset.UTF_8,
        )
    )
      .map((b) => ("0" + ((b + 256) % 256).toString(16)).slice(-2))
      .join("");
  function load() {
    const id = props().getProperty("STATE_FILE_ID");
    if (!id)
      throw new Error("Run initialize with approved configuration first");
    return JSON.parse(
      DriveApp.getFileById(id).getBlob().getDataAsString("UTF-8"),
    );
  }
  function persist(s) {
    DriveApp.getFileById(props().getProperty("STATE_FILE_ID")).setContent(
      LotteryCore.json(s),
    );
  }
  function locked(fn) {
    const lock = LockService.getScriptLock();
    lock.waitLock(30000);
    try {
      return fn();
    } finally {
      lock.releaseLock();
    }
  }
  function mutate(fn) {
    return locked(() => {
      const s = load();
      const result = fn(s);
      persist(s);
      return result;
    });
  }
  function requireAdmin(s) {
    LotteryCore.admin(s, actor());
  }
  function spreadsheet() {
    return SpreadsheetApp.openById(props().getProperty("PRIVATE_WORKBOOK_ID"));
  }
  function writeRows(sheet, headers, rows) {
    sheet.clearContents();
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    if (rows.length)
      sheet.getRange(2, 1, rows.length, headers.length).setValues(
        rows.map((r) =>
          headers.map((h) => {
            const v =
              r[h] == null
                ? ""
                : typeof r[h] === "object"
                  ? JSON.stringify(r[h])
                  : String(r[h]);
            return /^[=+@-]/.test(v) ? "'" + v : v;
          }),
        ),
      );
    sheet.setFrozenRows(1);
  }
  function materialize(s) {
    const book = spreadsheet();
    const tables = {
      Classes: s.classes,
      Submissions: s.submissions.map(({ raw, ...x }) => ({
        ...x,
        email: raw.email,
      })),
      Proposals: s.submissions.flatMap((e) =>
        e.raw.proposals.map((p, i) => ({
          submission_id: e.id,
          class_id: e.class_id,
          rank: i + 1,
          ...p,
          review: (e.decisions || [])[i] || null,
        })),
      ),
      "Duplicate Review": s.submissions
        .filter((x) => x.duplicate)
        .map((x) => ({ id: x.id, class_id: x.class_id, status: x.status })),
      "Booth Inventory": Object.entries(s.booths).map(([booth_id, b]) => ({
        booth_id,
        ...b,
      })),
      "Correction Requests": s.corrections,
      Lottery: s.run
        ? [
            {
              run_id: s.run.run_id,
              input_hash: s.run.input_hash,
              output_hash: s.run.output_hash,
            },
          ]
        : [],
      Confirmations: Object.entries(s.confirmations).map(([class_id, v]) => ({
        class_id,
        ...v,
      })),
      Exceptions: s.exceptions,
      "Audit Log": s.events,
      "Admin Dashboard": [
        {
          classes: s.classes.length,
          submissions: s.submissions.length,
          frozen: !!s.snapshot,
          committed: !!s.run,
        },
      ],
    };
    for (const [tab, rows] of Object.entries(tables)) {
      const headers = [...new Set(rows.flatMap((r) => Object.keys(r)))];
      writeRows(
        book.getSheetByName(tab) || book.insertSheet(tab),
        headers.length ? headers : ["status"],
        rows,
      );
    }
  }
  function initialize(config, classes) {
    return locked(() => {
      if (props().getProperty("STATE_FILE_ID"))
        throw new Error(
          "Already initialized; existing event cannot be overwritten",
        );
      if (!actor() || !config.admins.includes(actor()))
        throw new Error("Verified designated admin required");
      if (
        !config.retention_policy ||
        !config.sender_name ||
        !config.contact_verification_policy
      )
        throw new Error(
          "PTA retention, sender, contact verification policies required",
        );
      const s = LotteryCore.create(config, classes);
      const book =
        SpreadsheetApp.getActiveSpreadsheet() ||
        SpreadsheetApp.create("PRIVATE — " + config.event_id);
      TABS.forEach((t) => book.insertSheet(t));
      book.insertSheet("Form Responses").appendRow(["timestamp", "raw_json"]);
      const state = DriveApp.createFile(
        "PRIVATE lottery state " + config.event_id + ".json",
        LotteryCore.json(s),
        MimeType.PLAIN_TEXT,
      );
      props().setProperties({
        STATE_FILE_ID: state.getId(),
        PRIVATE_WORKBOOK_ID: book.getId(),
        DRY_RUN: "true",
      });
      // Sheet/form/state deliberately remain private: share only with the 2–3 designated admins manually.
      const form = FormApp.create(config.event_id + " — booth choices");
      form.setDescription(
        "Submit three choices acceptable to your class. Proposals remain private. PTA verifies your authority. After assignment, reply within 48 hours of the actual email send; no response means automatic acceptance. Late declines require PTA exception review.",
      );
      form.setCollectEmail(true);
      form
        .addListItem()
        .setTitle("class_id")
        .setChoiceValues(classes.map((c) => c.class_id))
        .setRequired(true);
      form.addTextItem().setTitle("name").setRequired(true);
      for (let rank = 1; rank <= 3; rank++) {
        form
          .addTextItem()
          .setTitle("name_" + rank)
          .setRequired(true);
        form
          .addParagraphTextItem()
          .setTitle("description_" + rank)
          .setRequired(true);
        form
          .addListItem()
          .setTitle("category_" + rank)
          .setChoiceValues(["game", "food"])
          .setRequired(true);
      }
      props().setProperty("FORM_ID", form.getId());
      ScriptApp.newTrigger("onFormSubmit")
        .forForm(form)
        .onFormSubmit()
        .create();
      ScriptApp.newTrigger("tick").timeBased().everyHours(1).create();
      materialize(s);
      return {
        private_workbook: book.getUrl(),
        form: form.getPublishedUrl(),
        dry_run: true,
      };
    });
  }
  function formSubmit(e) {
    return locked(() => {
      const s = load();
      const response = e.response;
      const values = Object.fromEntries(
        response
          .getItemResponses()
          .map((x) => [x.getItem().getTitle(), x.getResponse()]),
      );
      const raw = {
        class_id: values.class_id,
        name: values.name,
        email: response.getRespondentEmail(),
        proposals: [1, 2, 3].map((i) => ({
          name: values["name_" + i],
          description: values["description_" + i],
          category: values["category_" + i],
        })),
      };
      // Append the exact response values before normalization, including rejected/late intake.
      spreadsheet()
        .getSheetByName("Form Responses")
        .appendRow([
          now(),
          JSON.stringify({
            response_id: response.getId(),
            timestamp: response.getTimestamp().toISOString(),
            email: response.getRespondentEmail(),
            values,
          }),
        ]);
      try {
        const id = LotteryCore.intake(s, raw, now());
        persist(s);
        materialize(s);
        return id;
      } catch (error) {
        s.events.push({
          type: "INTAKE_REJECTED",
          at: now(),
          response_id: response.getId(),
          reason: error.message,
        });
        persist(s);
        throw error;
      }
    });
  }
  const methods = {
    verifyContact: LotteryCore.verifyContact,
    review: LotteryCore.review,
    correction: LotteryCore.correction,
    clearSignoffs: LotteryCore.clearSignoffs,
    resolveException: LotteryCore.resolveException,
  };
  function action(name, args) {
    return mutate((s) => {
      requireAdmin(s);
      if (!Object.hasOwn(methods, name))
        throw new Error("Unsupported admin operation");
      const value = methods[name](s, actor(), ...args, now());
      materialize(s);
      return value;
    });
  }
  function checkFeasibility() {
    return locked(() => {
      const s = load();
      requireAdmin(s);
      return LotteryCore.feasibility(s);
    });
  }
  function signoff() {
    return mutate((s) => {
      const result = LotteryCore.signoff(s, actor(), now(), hash);
      materialize(s);
      return result ? { input_hash: result.input_hash } : null;
    });
  }
  function exportSnapshot() {
    return locked(() => {
      const s = load();
      requireAdmin(s);
      if (!s.snapshot) throw new Error("Two-admin frozen snapshot required");
      const folder = DriveApp.createFolder(
        s.config.event_id + " frozen " + s.snapshot.input_hash,
      );
      for (const [name, bytes] of Object.entries(s.snapshot.files))
        folder.createFile(name, bytes, MimeType.PLAIN_TEXT);
      return folder.getUrl();
    });
  }
  function readBundle(folder) {
    const out = {};
    function walk(f, prefix) {
      const files = f.getFiles();
      while (files.hasNext()) {
        const file = files.next();
        const key = prefix + file.getName();
        if (Object.hasOwn(out, key))
          throw new Error("Duplicate bundle filename");
        out[key] = file.getBlob().getDataAsString("UTF-8");
      }
      const sub = f.getFolders();
      while (sub.hasNext()) {
        const next = sub.next();
        if (prefix || next.getName() !== "snapshot")
          throw new Error("Unexpected output directory");
        walk(next, "snapshot/");
      }
    }
    walk(folder, "");
    return out;
  }
  function importResults(folderId) {
    return mutate((s) => {
      requireAdmin(s);
      const result = LotteryCore.importRun(
        s,
        actor(),
        readBundle(DriveApp.getFolderById(folderId)),
        now(),
        hash,
      );
      materialize(s);
      return result;
    });
  }
  function newToken() {
    return Utilities.getUuid() + Utilities.getUuid() + Utilities.getUuid();
  }
  function sendMessage(to, subject, body) {
    // Gmail advanced service returns an actual message ID; MailApp cannot provide this receipt.
    const mime =
      "To: " +
      to +
      "\r\nSubject: " +
      subject.replace(/[\r\n]/g, " ") +
      "\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n" +
      body;
    const result = Gmail.Users.Messages.send(
      { raw: Utilities.base64EncodeWebSafe(mime, Utilities.Charset.UTF_8) },
      "me",
    );
    if (!result.id) throw new Error("Gmail returned no send receipt");
    return { message_id: result.id };
  }
  function sendAssignment(classId, kind) {
    return locked(() => {
      const s = load();
      requireAdmin(s);
      return deliver(s, classId, kind || "assignment");
    });
  }
  function deliver(s, classId, kind) {
    const token = newToken(),
      digest = hash(token);
    const prepared = LotteryCore.prepareMail(s, classId, kind, now(), digest);
    if (!prepared) return { skipped: true };
    const dry = props().getProperty("DRY_RUN") !== "false";
    // Persist intent BEFORE network send: interrupted or ambiguous sends remain SENDING and block retry.
    persist(s);
    let body =
      "Class " +
      classId +
      "\nAssigned booth: " +
      prepared.assignment.booth_id +
      "\nCategory: " +
      prepared.assignment.category +
      "\nAssigned rank: " +
      prepared.assignment.assigned_rank +
      "\n";
    if (kind === "assignment")
      body +=
        "Please accept or decline within 48 hours of this message being sent. No response is automatically accepted. The exact deadline is displayed by your private confirmation form. Confirm while signed into your PTA-verified email account: " +
        ScriptApp.getService().getUrl() +
        "?token=" +
        encodeURIComponent(token);
    else
      body +=
        "Reminder: confirmation deadline " +
        s.notifications[s.run.run_id + ":" + classId + ":assignment"]
          .deadline_at +
        ". No response is automatically accepted. Use the original private link.";
    if (dry) {
      LotteryCore.completeMail(s, prepared.key, { dry_run: true }, now());
      persist(s);
      return { dry_run: true, to: prepared.to, body };
    }
    try {
      const receipt = sendMessage(
        prepared.to,
        s.config.event_id + " private assignment",
        body,
      );
      LotteryCore.completeMail(s, prepared.key, receipt, now());
      persist(s);
      return receipt;
    } catch (error) {
      persist(s);
      throw new Error(
        "Send uncertain; reconcile " +
          prepared.key +
          " against Gmail Sent before retry. " +
          error.message,
      );
    }
  }
  function operationalMail(s, key, classId, subject, body) {
    if (s.notifications[key]) return { skipped: true };
    const c = s.classes.find((c) => c.class_id === classId);
    if (!c?.verified_email)
      throw new Error("Verified roster recipient required");
    s.notifications[key] = {
      key,
      class_id: classId,
      kind: "operational",
      to: c.verified_email,
      status: "SENDING",
      started_at: now(),
    };
    persist(s);
    if (props().getProperty("DRY_RUN") !== "false") {
      LotteryCore.completeMail(s, key, { dry_run: true }, now());
      persist(s);
      return { dry_run: true, body };
    }
    try {
      const receipt = sendMessage(c.verified_email, subject, body);
      LotteryCore.completeMail(s, key, receipt, now());
      persist(s);
      return receipt;
    } catch (error) {
      persist(s);
      throw new Error(
        "Send uncertain; manually reconcile " +
          key +
          " against Gmail Sent. " +
          error.message,
      );
    }
  }
  function sendCorrectionNotices(s) {
    for (const r of s.corrections.filter((x) => x.status === "OPEN"))
      operationalMail(
        s,
        "correction:" + r.id,
        r.class_id,
        s.config.event_id + " private correction request",
        "PTA requests a replacement or revision: " +
          r.reason +
          "\nDeadline: " +
          r.deadline +
          "\nSubmit three acceptable choices. Previous versions are preserved; no lottery advantage is offered.",
      );
  }
  function inviteRevisions(reason, deadline) {
    return locked(() => {
      const s = load();
      requireAdmin(s);
      if (s.snapshot) throw new Error("Frozen input cannot change");
      if (!reason || Date.parse(deadline) <= Date.now())
        throw new Error("Reason and future PTA deadline required");
      // Broad conservative outreach includes every potentially helpful class, never singles out a cause.
      for (const c of s.classes) {
        const r = LotteryCore.correction(
          s,
          actor(),
          c.class_id,
          reason,
          deadline,
          now(),
        );
        persist(s);
        operationalMail(
          s,
          "correction:" + r.id,
          c.class_id,
          s.config.event_id + " voluntary feasibility revision",
          "The current set cannot satisfy all allocation constraints. Every class is invited to voluntarily consider additional acceptable choices. No other proposals will be disclosed and no lottery advantage is promised. " +
            reason +
            " Deadline: " +
            deadline,
        );
      }
      return { invited: s.classes.length };
    });
  }
  function requestConsent(exceptionId, classId, boothId, deadline) {
    return locked(() => {
      const s = load();
      requireAdmin(s);
      const x = s.exceptions.find((x) => x.id === exceptionId),
        c = s.classes.find((c) => c.class_id === classId);
      if (
        !x ||
        x.status !== "OPEN" ||
        !x.affected.includes(classId) ||
        !c?.verified_email ||
        Date.parse(deadline) <= Date.now()
      )
        throw new Error(
          "Open exception, affected verified class and future deadline required",
        );
      LotteryCore.safe(boothId);
      if (!s.booths[boothId])
        throw new Error("Approved canonical booth required");
      const token = newToken(),
        digest = hash(token),
        key = "consent:" + exceptionId + ":" + classId + ":" + boothId;
      if (s.notifications[key]) return { skipped: true };
      s.tokens[digest] = {
        notification_key: key,
        purpose: "exception_consent",
        exception_id: exceptionId,
        class_id: classId,
        booth_id: boothId,
        category: s.booths[boothId]?.category,
        email: c.verified_email,
        run_id: s.run.run_id,
        used: false,
        expires: deadline,
      };
      persist(s);
      return operationalMail(
        s,
        key,
        classId,
        s.config.event_id + " explicit assignment change consent",
        "PTA requests your explicit consent to booth " +
          boothId +
          " (" +
          s.booths[boothId].category +
          ") for class " +
          classId +
          ". Reason: " +
          x.reason +
          " Deadline: " +
          deadline +
          ". No reply is NOT consent. Sign into your verified email, then use Accept to consent or Decline to refuse: " +
          ScriptApp.getService().getUrl() +
          "?token=" +
          encodeURIComponent(token),
      );
    });
  }
  function reconcile(key, receipt) {
    return mutate((s) =>
      LotteryCore.reconcileMail(s, actor(), key, receipt, now()),
    );
  }
  function scheduled() {
    return locked(() => {
      const s = load();
      const due = LotteryCore.tick(s, now());
      persist(s);
      for (const item of due) deliver(s, item.class_id, item.kind);
      if (!s.snapshot) {
        sendMissingNotices(s);
        sendCorrectionNotices(s);
      }
      materialize(s);
    });
  }
  function sendMissingNotices(s) {
    const notices = LotteryCore.missing(s, now());
    for (const n of notices) {
      if (n.status === "NOT_DUE") continue;
      const key = "intake:" + n.class_id + ":" + n.status;
      if (s.notifications[key]) continue;
      const c = s.classes.find((c) => c.class_id === n.class_id);
      if (!c.verified_email) continue;
      s.notifications[key] = {
        status: "SENDING",
        class_id: n.class_id,
        kind: n.status,
      };
      persist(s);
      if (props().getProperty("DRY_RUN") !== "false") {
        s.notifications[key].status = "DRY_RUN";
      } else {
        const r = sendMessage(
          c.verified_email,
          s.config.event_id + " submission " + n.status,
          "Please submit three booth proposals. Uniform grace deadline: " +
            n.deadline +
            ". Unresolved submissions go to PTA review; no draw advantage is offered.",
        );
        s.notifications[key] = {
          ...s.notifications[key],
          status: "SENT",
          message_id: r.message_id,
          sent_at: now(),
        };
      }
      persist(s);
    }
  }
  function resetDryRuns() {
    return mutate((s) => {
      requireAdmin(s);
      const removed = new Set();
      for (const [key, m] of Object.entries(s.notifications))
        if (m.status === "DRY_RUN") {
          removed.add(key);
          delete s.notifications[key];
        }
      for (const [digest, token] of Object.entries(s.tokens))
        if (removed.has(token.notification_key)) delete s.tokens[digest];
    });
  }
  function liveReadiness(s) {
    if (
      !s.config.retention_policy ||
      !s.config.contact_verification_policy ||
      !s.config.exception_approvers?.length ||
      !s.config.publication_approvers?.length ||
      !Number.isFinite(s.config.grace_hours) ||
      !s.config.initial_deadline ||
      !ScriptApp.getService().getUrl() ||
      !(
        s.config.identity_client_id ||
        s.config.confirmation_identity_policy === "trusted_workspace_session"
      )
    )
      throw new Error(
        "Unresolved PTA policy or web deployment blocks live mode",
      );
  }
  function setLive(enabled) {
    return locked(() => {
      const s = load();
      requireAdmin(s);
      if (enabled) liveReadiness(s);
      props().setProperty("DRY_RUN", enabled ? "false" : "true");
      return { dry_run: !enabled };
    });
  }
  function escape(text) {
    return String(text).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  }
  function recipientIdentity(e, s) {
    const credential = String(e.parameter.credential || "");
    if (!credential) {
      if (s.config.confirmation_identity_policy === "trusted_workspace_session")
        return actor();
      throw new Error("Verified Google identity required");
    }
    if (!s.config.identity_client_id)
      throw new Error("Google identity audience is not configured");
    const response = UrlFetchApp.fetch(
      "https://oauth2.googleapis.com/tokeninfo?id_token=" +
        encodeURIComponent(credential),
      { muteHttpExceptions: true },
    );
    if (response.getResponseCode() !== 200)
      throw new Error("Invalid identity token");
    const claims = JSON.parse(response.getContentText());
    if (
      claims.aud !== s.config.identity_client_id ||
      !["accounts.google.com", "https://accounts.google.com"].includes(
        claims.iss,
      ) ||
      !(claims.email_verified === true || claims.email_verified === "true") ||
      !Number.isFinite(Number(claims.exp)) ||
      Number(claims.exp) * 1000 <= Date.now()
    )
      throw new Error("Unverified identity token");
    return String(claims.email || "").toLowerCase();
  }
  function get(e) {
    const s = load(),
      token = String(e.parameter.token || "");
    const identity = s.config.identity_client_id
      ? '<script src="https://accounts.google.com/gsi/client" async defer></script><div id="g_id_onload" data-client_id="' +
        escape(s.config.identity_client_id) +
        '" data-callback="identityReady"></div><div class="g_id_signin" data-type="standard"></div><script>function identityReady(r){document.getElementById("credential").value=r.credential;document.getElementById("continue").disabled=false;}</script>'
      : "";
    return HtmlService.createHtmlOutput(
      "<h1>Private class confirmation</h1><p>Sign into your PTA-verified Google email to view your own assignment and exact deadline. No response within 48 hours of assignment email means automatic acceptance. Late declines are routed to PTA.</p>" +
        identity +
        '<form method="post" action="' +
        escape(ScriptApp.getService().getUrl()) +
        '"><input type="hidden" name="token" value="' +
        escape(token) +
        '"><input type="hidden" name="action" value="details"><input id="credential" type="hidden" name="credential"><button id="continue" ' +
        (s.config.identity_client_id ? "disabled" : "") +
        ">View private details</button></form>",
    );
  }
  function details(s, token, digest, identity, credential) {
    const t = s.tokens[digest];
    if (
      !t ||
      t.used ||
      t.email !== identity ||
      t.run_id !== s.run.run_id ||
      !t.expires
    )
      throw new Error("Invalid private details token");
    const assignment =
      t.purpose === "exception_consent"
        ? { booth_id: t.booth_id, category: t.category }
        : s.roster.find((a) => a.class_id === t.class_id);
    const deadline =
      t.purpose === "exception_consent"
        ? t.expires
        : s.notifications[t.notification_key]?.deadline_at;
    if (!deadline) throw new Error("Actual sent deadline unavailable");
    return HtmlService.createHtmlOutput(
      "<h1>" +
        escape(
          t.purpose === "exception_consent"
            ? "Explicit change consent"
            : "Private assignment",
        ) +
        "</h1><p>Class " +
        escape(t.class_id) +
        "; booth " +
        escape(assignment.booth_id) +
        "; category " +
        escape(assignment.category) +
        (assignment.assigned_rank
          ? "; assigned rank " + escape(assignment.assigned_rank)
          : "") +
        "</p><p>Exact deadline: " +
        escape(deadline) +
        ". " +
        (t.purpose === "exception_consent"
          ? "No response is never consent."
          : "No response is automatically accepted; late declines require PTA review.") +
        '</p><form method="post" action="' +
        escape(ScriptApp.getService().getUrl()) +
        '"><input type="hidden" name="token" value="' +
        escape(token) +
        '"><input type="hidden" name="credential" value="' +
        escape(credential) +
        '"><button name="response" value="accept">Accept</button><button name="response" value="decline">Decline</button></form>',
    );
  }
  function post(e) {
    try {
      return mutate((s) => {
        const digest = hash(String(e.parameter.token || "")),
          identity = recipientIdentity(e, s),
          token = s.tokens[digest];
        if (e.parameter.action === "details")
          return details(
            s,
            String(e.parameter.token || ""),
            digest,
            identity,
            String(e.parameter.credential || ""),
          );
        let status;
        if (token?.purpose === "exception_consent") {
          if (
            token.used ||
            token.email !== identity ||
            token.run_id !== s.run.run_id ||
            token.category !== s.booths[token.booth_id]?.category ||
            Date.now() >= Date.parse(token.expires)
          )
            throw new Error("Invalid consent token");
          if (e.parameter.response === "accept") {
            LotteryCore.consent(
              s,
              token.exception_id,
              identity,
              token.class_id,
              token.booth_id,
              now(),
            );
            status = "CONSENT_RECORDED";
          } else if (e.parameter.response === "decline") {
            status = "CONSENT_REFUSED";
            s.events.push({
              type: "CONSENT_REFUSED",
              class_id: token.class_id,
              exception_id: token.exception_id,
              at: now(),
            });
          } else throw new Error("Invalid response");
          token.used = true;
        } else
          status = LotteryCore.respond(
            s,
            digest,
            identity,
            String(e.parameter.response || ""),
            now(),
          );
        materialize(s);
        return HtmlService.createHtmlOutput(escape(status));
      });
    } catch (error) {
      return HtmlService.createHtmlOutput("Response rejected. Contact PTA.");
    }
  }
  function openException(type, affected, reason) {
    return mutate((s) => {
      requireAdmin(s);
      return LotteryCore.addException(
        s,
        type,
        affected,
        reason,
        actor(),
        now(),
      );
    });
  }
  function recordConsent(id, classId, boothId) {
    return mutate((s) =>
      LotteryCore.consent(s, id, actor(), classId, boothId, now()),
    );
  }
  function shareReadOnly(file, policy) {
    if (policy && policy.anyone_with_link === true)
      file.setSharing(
        DriveApp.Access.ANYONE_WITH_LINK,
        DriveApp.Permission.VIEW,
      );
    else if (policy && Array.isArray(policy.viewers) && policy.viewers.length)
      file.addViewers(policy.viewers);
    else
      throw new Error(
        "PTA must explicitly approve a read-only publication audience",
      );
  }
  function publish() {
    return locked(() => {
      const s = load(),
        p = LotteryCore.publication(s, actor(), now());
      persist(s);
      if (p.status === "PUBLISHED" || p.status !== "APPROVED") return p;
      const actual = s.publications.find((x) => x.version === p.version);
      if (!s.config.publication_audience)
        throw new Error("Approved publication audience required");
      let book;
      if (actual.sheet_id) book = SpreadsheetApp.openById(actual.sheet_id);
      else {
        book = SpreadsheetApp.create(
          s.config.event_id + " final roster v" + p.version,
        );
        actual.sheet_id = book.getId();
        actual.sheet_link = book.getUrl();
        persist(s);
      }
      const rows = p.entries.map((a) => ({
        class: s.classes.find((c) => c.class_id === a.class_id).display_name,
        booth: s.booths[a.booth_id]?.name || a.booth_id,
        category: a.category,
      }));
      writeRows(book.getSheets()[0], ["class", "booth", "category"], rows);
      SpreadsheetApp.flush();
      if (!actual.pdf_reference) {
        const response = UrlFetchApp.fetch(
          "https://docs.google.com/spreadsheets/d/" +
            book.getId() +
            "/export?format=pdf&size=letter&portrait=true&fitw=true&sheetnames=false&gridlines=false",
          {
            headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
            muteHttpExceptions: true,
          },
        );
        if (response.getResponseCode() !== 200)
          throw new Error(
            "PDF export failed; retry reuses prepared roster sheet",
          );
        const pdf = DriveApp.createFile(
          response
            .getBlob()
            .setName(s.config.event_id + "-roster-v" + p.version + ".pdf"),
        );
        actual.pdf_reference = pdf.getId();
        persist(s);
      }
      shareReadOnly(
        DriveApp.getFileById(actual.sheet_id),
        s.config.publication_audience,
      );
      shareReadOnly(
        DriveApp.getFileById(actual.pdf_reference),
        s.config.publication_audience,
      );
      actual.published_at = now();
      actual.status = "PUBLISHED";
      persist(s);
      return actual;
    });
  }
  function dashboard() {
    return locked(() => {
      const s = load();
      requireAdmin(s);
      const book = SpreadsheetApp.create(
        s.config.event_id + " sanitized officer dashboard",
      );
      writeRows(
        book.getSheets()[0],
        ["class_id", "submission_status", "confirmation_status"],
        s.classes.map((c) => ({
          class_id: c.class_id,
          submission_status: s.submissions.some(
            (e) => e.class_id === c.class_id && e.status === "AUTHORITATIVE",
          )
            ? "VERIFIED"
            : "PENDING",
          confirmation_status: s.confirmations[c.class_id]?.status || "PENDING",
        })),
      );
      shareReadOnly(DriveApp.getFileById(book.getId()), {
        viewers: s.config.officer_viewers,
      });
      return book.getUrl();
    });
  }
  return {
    initialize,
    formSubmit,
    action,
    signoff,
    checkFeasibility,
    exportSnapshot,
    importResults,
    sendAssignment,
    reconcile,
    scheduled,
    resetDryRuns,
    setLive,
    get,
    post,
    openException,
    recordConsent,
    requestConsent,
    inviteRevisions,
    publish,
    dashboard,
    hash,
    escape,
  };
})();
function onFormSubmit(e) {
  return LotteryApp.formSubmit(e);
}
function doGet(e) {
  return LotteryApp.get(e);
}
function doPost(e) {
  return LotteryApp.post(e);
}
function tick() {
  return LotteryApp.scheduled();
}
function adminAction(name, args) {
  return LotteryApp.action(name, args);
}
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("PTA Lottery")
    .addItem("Private administration", "showLotteryAdmin")
    .addToUi();
}
function showLotteryAdmin() {
  SpreadsheetApp.getUi().showSidebar(
    HtmlService.createHtmlOutputFromFile("Admin").setTitle("PTA Lottery"),
  );
}
function adminUiAction(name, args) {
  if (!Array.isArray(args)) throw new Error("Arguments must be a JSON array");
  const operations = {
    initialize: LotteryApp.initialize,
    requestConsent: LotteryApp.requestConsent,
    inviteRevisions: LotteryApp.inviteRevisions,
    signoff: LotteryApp.signoff,
    checkFeasibility: LotteryApp.checkFeasibility,
    exportSnapshot: LotteryApp.exportSnapshot,
    importResults: LotteryApp.importResults,
    sendAssignment: LotteryApp.sendAssignment,
    reconcile: LotteryApp.reconcile,
    openException: LotteryApp.openException,
    publish: LotteryApp.publish,
    dashboard: LotteryApp.dashboard,
    resetDryRuns: LotteryApp.resetDryRuns,
    setLive: LotteryApp.setLive,
  };
  if (Object.hasOwn(operations, name)) return operations[name](...args);
  return LotteryApp.action(name, args);
}
