import assert from "node:assert/strict";
import test from "node:test";
import { hostWorkspacePath, workspaceEnv } from "./configure-docker-workspace.mjs";

test("native development uses the local task workspace", () => {
  assert.equal(hostWorkspacePath("/Users/dev/project/.workspaces", null), "/Users/dev/project/.workspaces");
});

test("dev container maps only the task workspace to its host source", () => {
  assert.equal(hostWorkspacePath("/workspaces/project/.workspaces", [
    { Type: "bind", Source: "/Users/dev/My Project", Destination: "/workspaces/project" },
    { Type: "bind", Source: "/Users/dev/.ssh", Destination: "/mnt/host-ssh" },
  ]), "/Users/dev/My Project/.workspaces");
});

test("the most specific mount wins", () => {
  assert.equal(hostWorkspacePath("/workspaces/project/.workspaces", [
    { Type: "bind", Source: "/Users/dev/project", Destination: "/workspaces/project" },
    { Type: "bind", Source: "/Volumes/tasks", Destination: "/workspaces/project/.workspaces" },
  ]), "/Volumes/tasks");
});

test("unmapped paths and named volumes do not fall back to container paths", () => {
  assert.throws(() => hostWorkspacePath("/workspaces/project/.workspaces", []), /not backed/);
  assert.throws(() => hostWorkspacePath("/workspaces/project/.workspaces", [
    { Type: "bind", Source: "/Users/dev/other", Destination: "/workspaces/pro" },
  ]), /not backed/);
  assert.throws(() => hostWorkspacePath("/workspaces/project/.workspaces", [
    { Type: "bind", Source: "/Users/dev/project", Destination: "/workspaces/project" },
    { Type: "volume", Source: "/var/lib/docker/volumes/tasks/_data", Destination: "/workspaces/project/.workspaces" },
  ]), /not backed/);
});

test("environment update preserves unrelated values and replaces duplicate mappings", () => {
  const input = "# Settings\nTOKEN='keep-me'\nWORKBENCH_DOCKER_WORKSPACE_HOST=/old\nexport WORKBENCH_DOCKER_WORKSPACE_HOST=/older\nOTHER=value";
  const output = workspaceEnv(input, "/Users/dev/project/.workspaces");
  assert.equal(output, "# Settings\nTOKEN='keep-me'\nOTHER=value\nWORKBENCH_DOCKER_WORKSPACE_HOST='/Users/dev/project/.workspaces'\n");
  assert.equal(workspaceEnv(output, "/Users/dev/project/.workspaces"), output);
});

test("environment update preserves CRLF settings and commented examples", () => {
  assert.equal(
    workspaceEnv("# WORKBENCH_DOCKER_WORKSPACE_HOST=example\r\nOTHER=value\r\nWORKBENCH_DOCKER_WORKSPACE_HOST=/old\r\n", "/host/.workspaces"),
    "# WORKBENCH_DOCKER_WORKSPACE_HOST=example\r\nOTHER=value\r\nWORKBENCH_DOCKER_WORKSPACE_HOST='/host/.workspaces'\n",
  );
});

test("workspace values are quoted without expanding dollars, hashes, or spaces", () => {
  assert.equal(
    workspaceEnv("", "/Users/dev/My $Project #1's/.workspaces"),
    "WORKBENCH_DOCKER_WORKSPACE_HOST='/Users/dev/My $Project #1\\'s/.workspaces'\n",
  );
});

test("invalid workspace values fail explicitly", () => {
  for (const value of ["", "/", "./.workspaces", "/tmp/tasks\nOTHER=value", "/tmp/\0tasks"]) {
    assert.throws(() => workspaceEnv("", value), /absolute path/);
  }
});
