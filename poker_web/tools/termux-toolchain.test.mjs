import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("TypeScript CLI starts on Android ARM64 without a platform executable", () => {
  const compiler = new URL("../node_modules/typescript/bin/tsc", import.meta.url).href;
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `Object.defineProperty(process, "platform", { value: "android" });
       Object.defineProperty(process, "arch", { value: "arm64" });
       process.argv = [process.execPath, ${JSON.stringify(compiler)}, "--version"];
       await import(${JSON.stringify(compiler)});`,
    ],
    {
      cwd: fileURLToPath(new URL("../", import.meta.url)),
      encoding: "utf8",
      timeout: 15000,
      windowsHide: true,
    },
  );
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, (result.stderr + result.stdout).slice(-4000));
  assert.match(result.stdout, /^Version \d+\./m);
});
