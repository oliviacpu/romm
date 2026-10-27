import { describe, expect, it, vi } from "vitest";
import { droppedFiles, uploadPath } from "./uploadFiles";

function fileEntry(file: File): FileSystemFileEntry {
  return {
    name: file.name,
    isFile: true,
    isDirectory: false,
    file: (success: FileCallback) => success(file),
  } as FileSystemFileEntry;
}

describe("directory upload paths", () => {
  it("keeps the selected directory and nested path", () => {
    const file = new File(["track"], "track01.iso");
    Object.defineProperty(file, "webkitRelativePath", {
      value: "Crazy Taxi/disc/track01.iso",
    });
    expect(uploadPath(file)).toBe("Crazy Taxi/disc/track01.iso");
  });

  it("reads every directory page and keeps equal basenames apart", async () => {
    const first = new File(["one"], "track01.iso");
    const second = new File(["two"], "track01.iso");
    const transfer = new DataTransfer();
    for (const [name, file] of [
      ["Game A", first],
      ["Game B", second],
    ] as const) {
      const readEntries = vi
        .fn()
        .mockImplementationOnce((success: FileSystemEntriesCallback) =>
          success([fileEntry(file)]),
        )
        .mockImplementationOnce((success: FileSystemEntriesCallback) =>
          success([fileEntry(new File(["index"], "disc.gdi"))]),
        )
        .mockImplementationOnce((success: FileSystemEntriesCallback) =>
          success([]),
        );
      const folder = {
        name,
        fullPath: `/${name}`,
        isFile: false,
        isDirectory: true,
        filesystem: { name, root: null! },
        getParent: vi.fn(),
        getDirectory: vi.fn(),
        getFile: vi.fn(),
        createReader: () => ({ readEntries }),
      } as FileSystemDirectoryEntry;
      transfer.items.add(file);
      const item = transfer.items[transfer.items.length - 1];
      if (!item) throw new Error("Missing transfer item");
      Object.defineProperty(item, "webkitGetAsEntry", { value: () => folder });
    }

    const files = await droppedFiles(transfer.items);
    expect(files.map(uploadPath)).toEqual([
      "Game A/track01.iso",
      "Game A/disc.gdi",
      "Game B/track01.iso",
      "Game B/disc.gdi",
    ]);
    expect(await files[0]?.text()).toBe("one");
    expect(await files[2]?.text()).toBe("two");
  });
});
