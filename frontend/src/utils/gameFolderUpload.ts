import { uploadPath } from "@/utils/uploadFiles";

export type GameFolderError =
  "one-folder" | "disc-folders" | "disc-order" | "game-name" | "duplicate-path";

export type GameFolderPlan =
  | { ok: true; name: string; paths: Map<File, string> }
  | { ok: false; error: GameFolderError };

const discSuffix = /(?:^|[\s_.(-])(?:disc|disk|cd|gd)[\s_.-]*([1-8])\)?$/i;

export function suggestedGameName(path: string): string {
  const root = path.split("/")[0] ?? "";
  const withoutDisc = root.replace(discSuffix, "").replace(/[\s_.(-]+$/, "");
  return (withoutDisc || (discSuffix.test(root) ? "" : root)).replaceAll(
    "_",
    " ",
  );
}

export function gameFolderPlan(
  files: File[],
  name: string,
  multiDisc: boolean,
): GameFolderPlan {
  const title = name.trim();
  if (!title || title.startsWith(".") || /[/\\\x00-\x1f]/.test(title)) {
    return { ok: false, error: "game-name" };
  }
  if (
    !multiDisc &&
    new Set(files.map((file) => uploadPath(file).split("/")[0])).size !== 1
  ) {
    return { ok: false, error: "one-folder" };
  }
  const roots = new Map<string, number>();
  const paths = new Map<File, string>();
  const seen = new Set<string>();
  for (const file of files) {
    const original = uploadPath(file);
    const slash = original.indexOf("/");
    if (slash < 1 || slash === original.length - 1) {
      return { ok: false, error: multiDisc ? "disc-folders" : "one-folder" };
    }
    const root = original.slice(0, slash);
    let prefix = "";
    if (multiDisc) {
      const match = root.match(discSuffix);
      if (!match) return { ok: false, error: "disc-folders" };
      const number = Number(match[1]);
      roots.set(root, number);
      prefix = `Disc ${number}/`;
    } else {
      roots.set(root, 0);
    }
    const relative = prefix + original.slice(slash + 1);
    if (seen.has(relative.toLocaleLowerCase())) {
      return { ok: false, error: "duplicate-path" };
    }
    seen.add(relative.toLocaleLowerCase());
    paths.set(file, relative);
  }
  if (!multiDisc && roots.size !== 1) return { ok: false, error: "one-folder" };
  if (multiDisc) {
    const numbers = [...roots.values()].sort((a, b) => a - b);
    if (
      numbers.length < 2 ||
      numbers.some((number, index) => number !== index + 1)
    ) {
      return { ok: false, error: "disc-order" };
    }
  }
  return { ok: true, name: title, paths };
}
