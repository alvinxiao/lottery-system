"use strict";
const fs = require("node:fs"),
  path = require("node:path");
const root = path.resolve(__dirname, ".."),
  out = path.join(root, "dist");
fs.mkdirSync(out, { recursive: true });
for (const name of ["Core", "App"])
  fs.copyFileSync(
    path.join(root, "src", name + ".js"),
    path.join(out, name + ".gs"),
  );
fs.copyFileSync(
  path.join(root, "src", "Admin.html"),
  path.join(out, "Admin.html"),
);
fs.copyFileSync(
  path.join(root, "appsscript.json"),
  path.join(out, "appsscript.json"),
);
console.log(
  "Deployable Apps Script sources: google/dist (no network calls performed).",
);
