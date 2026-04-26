const { spawnSync } = require("child_process");

const candidates = process.platform === "win32"
  ? [["py", ["-3"]], ["python", []], ["python3", []]]
  : [["python3", []], ["python", []]];

const args = process.argv.slice(2);

for (const [command, prefix] of candidates) {
  const result = spawnSync(command, [...prefix, ...args], { stdio: "inherit" });
  if (result.error && result.error.code === "ENOENT") continue;
  process.exit(result.status ?? 1);
}

console.error("No Python 3 runtime found. Install Python 3 or set it on PATH.");
process.exit(1);
