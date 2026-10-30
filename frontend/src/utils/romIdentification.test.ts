import { describe, expect, it } from "vitest";
import { inspectionConflict, inspectionSample } from "./romIdentification";

const result = {
  format: "cartridge",
  platforms: ["n64"],
  evidence: "header",
  invalid: false,
  members: [],
  incompatible_platforms: [],
};

describe("ROM content inspection", () => {
  it("samples only the server's bounded head and tail", async () => {
    const file = new File([Uint8Array.from([0, 1, 2, 3, 4, 5])], "test.bin");
    expect(
      await inspectionSample(file, { head_bytes: 2, tail_bytes: 3 }),
    ).toEqual({
      filename: "test.bin",
      size: 6,
      head: "AAE=",
      tail: "AwQF",
    });
  });

  it("handles small and empty files without negative slicing", async () => {
    expect(
      await inspectionSample(new File([], "empty"), {
        head_bytes: 128,
        tail_bytes: 1024,
      }),
    ).toEqual({
      filename: "empty",
      size: 0,
      head: "",
      tail: "",
    });
    const sample = await inspectionSample(new File(["abc"], "small"), {
      head_bytes: 128,
      tail_bytes: 1024,
    });
    expect(sample.head).toBe("YWJj");
    expect(sample.tail).toBe(sample.head);
  });

  it("rejects mismatches, mixed archives, invalid archives and incompatible containers", () => {
    expect(inspectionConflict(result, "n64")).toBe(false);
    expect(inspectionConflict(result, "dc")).toBe(true);
    expect(
      inspectionConflict({ ...result, platforms: ["n64", "genesis"] }, "n64"),
    ).toBe(true);
    expect(
      inspectionConflict({ ...result, platforms: [], invalid: true }, "n64"),
    ).toBe(true);
    expect(
      inspectionConflict(
        { ...result, platforms: [], incompatible_platforms: ["n64"] },
        "n64",
      ),
    ).toBe(true);
    expect(inspectionConflict({ ...result, platforms: [] }, "dc")).toBe(false);
  });
});
