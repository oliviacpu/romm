import type { PlatformUploadPolicy } from "@/services/api/rom";

export type UploadIssue =
  | { kind: "unsupported"; file: string }
  | { kind: "needs-folder"; file: string }
  | { kind: "launch-count"; disc: string }
  | { kind: "descriptor"; file: string }
  | { kind: "missing-track"; file: string }
  | { kind: "unreferenced-track"; file: string };

function extension(path: string): string {
  return path.slice(path.lastIndexOf(".")).toLowerCase();
}

function discName(path: string): string {
  const first = path.split("/")[0] ?? "";
  return /^Disc [1-8]$/.test(first) ? first : "";
}

export function singleFileIssue(
  files: File[],
  policy: PlatformUploadPolicy | undefined,
): UploadIssue | null {
  if (!policy) return null;
  for (const file of files) {
    const ext = extension(file.name);
    if ((ext === ".gdi" || ext === ".cue") && policy.launch.includes(ext)) {
      return { kind: "needs-folder", file: file.name };
    }
    if (!policy.launch.includes(ext)) {
      return { kind: "unsupported", file: file.name };
    }
  }
  return null;
}

function trackNames(name: string, content: string): string[] | null {
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (extension(name) === ".gdi") {
    const count = Number(lines.shift());
    if (!Number.isInteger(count) || count !== lines.length || count < 1) {
      return null;
    }
    const tracks = lines.map(
      (line) =>
        line.match(
          /^\d+\s+\d+\s+\d+\s+\d+\s+(?:"([^"]+)"|(\S+))\s+\d+$/,
        )?.[1] ??
        line.match(/^\d+\s+\d+\s+\d+\s+\d+\s+(?:"([^"]+)"|(\S+))\s+\d+$/)?.[2],
    );
    return tracks.every(Boolean) ? (tracks as string[]) : null;
  }
  const tracks = lines
    .filter((line) => /^FILE\s+/i.test(line))
    .map(
      (line) =>
        line.match(/^FILE\s+(?:"([^"]+)"|(\S+))\s+/i)?.[1] ??
        line.match(/^FILE\s+(?:"([^"]+)"|(\S+))\s+/i)?.[2],
    );
  return tracks.length && tracks.every(Boolean) ? (tracks as string[]) : null;
}

export async function folderIssue(
  paths: Map<File, string>,
  policy: PlatformUploadPolicy | undefined,
): Promise<UploadIssue | null> {
  if (!policy) return null;
  const byDisc = new Map<string, Array<[File, string]>>();
  for (const entry of paths) {
    const disc = discName(entry[1]);
    byDisc.set(disc, [...(byDisc.get(disc) ?? []), entry]);
  }
  for (const [disc, entries] of byDisc) {
    const launch = entries.filter(([, path]) =>
      policy.launch.includes(extension(path)),
    );
    if (launch.length !== 1) return { kind: "launch-count", disc };
    const [descriptor, descriptorPath] = launch[0]!;
    if (![".gdi", ".cue"].includes(extension(descriptorPath))) {
      const companion = entries.find(([, path]) =>
        policy.companions.includes(extension(path)),
      );
      if (companion) return { kind: "unreferenced-track", file: companion[1] };
      continue;
    }
    if (descriptor.size > 1024 * 1024) {
      return { kind: "descriptor", file: descriptorPath };
    }
    const tracks = trackNames(descriptorPath, await descriptor.text());
    if (!tracks) return { kind: "descriptor", file: descriptorPath };
    const parent = descriptorPath.slice(0, descriptorPath.lastIndexOf("/") + 1);
    const selected = new Set(entries.map(([, path]) => path));
    const referenced = new Set<string>();
    for (const track of tracks) {
      if (track.startsWith("/") || track.split("/").includes("..")) {
        return { kind: "descriptor", file: descriptorPath };
      }
      const path = `${parent}${track}`;
      if (!selected.has(path)) return { kind: "missing-track", file: path };
      referenced.add(path);
    }
    const extra = entries.find(
      ([, path]) =>
        policy.companions.includes(extension(path)) && !referenced.has(path),
    );
    if (extra) return { kind: "unreferenced-track", file: extra[1] };
  }
  return null;
}
