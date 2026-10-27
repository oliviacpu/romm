import { describe, expect, it } from "vitest";
import { folderIssue, singleFileIssue } from "./uploadPolicy";

const dreamcast = {
  label: "Dreamcast",
  launch: [".gdi", ".cue", ".chd", ".cdi"],
  companions: [".iso", ".raw", ".bin"],
};

describe("upload playability preflight", () => {
  it("blocks a standalone Dreamcast ISO but accepts a GameCube ISO", () => {
    const iso = new File(["data"], "JETRADIO.iso");
    expect(singleFileIssue([iso], dreamcast)).toEqual({
      kind: "unsupported",
      file: "JETRADIO.iso",
    });
    expect(
      singleFileIssue([iso], {
        label: "GameCube",
        launch: [".iso"],
        companions: [],
      }),
    ).toBeNull();
    expect(
      singleFileIssue([new File(["data"], "disc.gdi")], dreamcast),
    ).toEqual({
      kind: "needs-folder",
      file: "disc.gdi",
    });
  });

  it("allows single-file Dreamcast CHD and CDI images", () => {
    expect(
      singleFileIssue([new File(["disc"], "game.chd")], dreamcast),
    ).toBeNull();
    expect(
      singleFileIssue([new File(["disc"], "game.cdi")], dreamcast),
    ).toBeNull();
  });

  it("accepts referenced ISO tracks and rejects a missing track before transfer", async () => {
    const descriptor = new File(
      ["2\n1 0 4 2048 track01.iso 0\n2 775 0 2352 track02.raw 0\n"],
      "disc.gdi",
    );
    const tracks = new Map<File, string>([
      [descriptor, "disc.gdi"],
      [new File(["data"], "track01.iso"), "track01.iso"],
      [new File(["data"], "track02.raw"), "track02.raw"],
    ]);
    expect(await folderIssue(tracks, dreamcast)).toBeNull();
    tracks.delete([...tracks.keys()][2]!);
    expect(await folderIssue(tracks, dreamcast)).toEqual({
      kind: "missing-track",
      file: "track02.raw",
    });
  });

  it("requires one launch image for each disc", async () => {
    const paths = new Map<File, string>([
      [new File(["game"], "disc1.chd"), "Disc 1/disc1.chd"],
      [new File(["game"], "disc2.chd"), "Disc 2/disc2.chd"],
    ]);
    expect(await folderIssue(paths, dreamcast)).toBeNull();
    paths.delete([...paths.keys()][1]!);
    paths.set(new File(["track"], "track.iso"), "Disc 2/track.iso");
    expect(await folderIssue(paths, dreamcast)).toEqual({
      kind: "launch-count",
      disc: "Disc 2",
    });
  });
});
