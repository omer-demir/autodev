import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { hostname } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const variable = "WORKBENCH_DOCKER_WORKSPACE_HOST";

export function hostWorkspacePath(workspace, mounts) {
  if (mounts === null) return workspace;
  const mount = mounts
    .filter(({ Destination }) =>
      workspace === Destination || workspace.startsWith(`${Destination.replace(/\/$/, "")}/`))
    .sort((a, b) => b.Destination.length - a.Destination.length)[0];
  if (!mount || mount.Type !== "bind") {
    throw new Error(
      "The task workspace is not backed by a host bind mount. " +
      `Set ${variable} to a host directory that maps to this project's .workspaces directory.`,
    );
  }
  return path.posix.join(mount.Source, path.posix.relative(mount.Destination, workspace));
}

export function workspaceEnv(contents, workspace) {
  if (!path.posix.isAbsolute(workspace) || workspace === "/" || /[\r\n\0]/.test(workspace)) {
    throw new Error(`${variable} must be an absolute path to the project's task workspace directory.`);
  }
  const previous = new RegExp(`^[ \\t]*(?:export[ \\t]+)?${variable}[ \\t]*=[^\\r\\n]*(?:\\r?\\n|$)`, "gm");
  const preserved = contents.replace(previous, "");
  const separator = preserved && !preserved.endsWith("\n") ? "\n" : "";
  return `${preserved}${separator}${variable}='${workspace.replaceAll("'", "\\'")}'\n`;
}

function configure() {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const workspace = path.join(root, ".workspaces");
  let host = process.env[variable];
  if (!host) {
    let mounts = null;
    if (existsSync("/.dockerenv") || existsSync("/run/.containerenv")) {
      try {
        mounts = JSON.parse(execFileSync(
          "docker", ["inspect", hostname(), "--format", "{{json .Mounts}}"],
          { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
        ));
      } catch (error) {
        throw new Error(
          `Cannot inspect this dev container through Docker. Check the daemon connection, or set ${variable} explicitly.`,
          { cause: error },
        );
      }
    }
    host = hostWorkspacePath(workspace, mounts);
  }
  const envPath = path.join(root, ".env");
  const contents = existsSync(envPath) ? readFileSync(envPath, "utf8") : "";
  const updated = workspaceEnv(contents, host);
  mkdirSync(path.join(workspace, ".agentmesh"), { recursive: true });
  writeFileSync(envPath, updated, { mode: 0o600 });
  console.log(`Docker task workspace: ${host}`);
  console.log("Saved workspace mapping in .env; other settings were preserved.");
  console.log("If Docker Desktop requests file sharing, approve only this directory, not your home or filesystem root.");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    configure();
  } catch (error) {
    console.error(`Docker workspace setup failed: ${error.message}`);
    process.exitCode = 1;
  }
}
