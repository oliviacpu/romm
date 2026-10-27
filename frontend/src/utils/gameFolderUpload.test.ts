import { describe, expect, it } from "vitest";
import { gameFolderPlan, suggestedGameName } from "./gameFolderUpload";

function selected(path: string): File {
  const file = new File(["data"], path.split("/").at(-1) ?? "file");
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

describe("game folder planning", () => {
  it("keeps two complete discs inside one RomM game", () => {
    const files = [
      selected("Skies of Arcadia/Disc 1/disc.gdi"),
      selected("Skies of Arcadia/Disc 1/track01.iso"),
      selected("Skies of Arcadia/Disc 2/disc.gdi"),
      selected("Skies of Arcadia/Disc 2/track01.iso"),
    ];
    const plan = gameFolderPlan(files, "Skies of Arcadia", false);
    expect(plan.ok).toBe(true);
    if (!plan.ok) return;
    expect([...plan.paths.values()]).toEqual([
      "Disc 1/disc.gdi",
      "Disc 1/track01.iso",
      "Disc 2/disc.gdi",
      "Disc 2/track01.iso",
    ]);
  });

  it("combines separately selected GD1 and GD2 folders", () => {
    const files = [
      selected("Skies_Of_Arcadia_GD1/track01.iso"),
      selected("Skies_Of_Arcadia_GD2/track01.iso"),
    ];
    expect(suggestedGameName("Skies_Of_Arcadia_GD1/track01.iso")).toBe(
      "Skies Of Arcadia",
    );
    const plan = gameFolderPlan(files, "Skies of Arcadia", true);
    expect(plan.ok).toBe(true);
    if (!plan.ok) return;
    expect([...plan.paths.values()]).toEqual([
      "Disc 1/track01.iso",
      "Disc 2/track01.iso",
    ]);
  });

  it("refuses incomplete or ambiguous disc selections", () => {
    expect(
      gameFolderPlan([selected("Game_GD1/disc.gdi")], "Game", true),
    ).toEqual({ ok: false, error: "disc-order" });
    expect(
      gameFolderPlan(
        [selected("Game_GD1/disc.gdi"), selected("Game_GD3/disc.gdi")],
        "Game",
        true,
      ),
    ).toEqual({ ok: false, error: "disc-order" });
    expect(
      gameFolderPlan(
        [selected("Game A/disc.gdi"), selected("Game B/disc.gdi")],
        "Game",
        false,
      ),
    ).toEqual({ ok: false, error: "one-folder" });
  });
});
